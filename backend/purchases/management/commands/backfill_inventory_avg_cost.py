from datetime import datetime, time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import Invoice, InvoiceItem, Return, ReturnItem
from purchases.models import (
    Inventory, LostInventoryItem, LostInventoryRecovery, PurchaseItem,
    PurchaseOrder, PurchaseReturn, PurchaseReturnItem,
)


def _as_datetime(value):
    """Normalizes a date or datetime to an aware datetime at local midnight
    (dates) so every event source sorts on one comparable timeline. Events
    that only have a DateField (LostInventoryRecovery.recovered_at) lose
    intra-day ordering against same-day datetime events — an accepted,
    unavoidable precision limit of reconstructing history from what was
    actually recorded, not a correctness bug in the replay itself."""
    if isinstance(value, datetime):
        return value
    return timezone.make_aware(datetime.combine(value, time.min))


class Command(BaseCommand):
    """
    One-time historical reconstruction of Inventory.avg_unit_cost — replays
    EVERY event that ever changed a product's stock, in the order it really
    happened, and recalculates the moving average ONLY at purchase events
    (using the real quantity-on-hand at that moment as the weight) — exactly
    matching the invariant purchases.services.sync_inventory() now enforces
    going forward. Neutral events (sales, returns either direction, lost,
    recovered) only move the replayed quantity, never the average.

    This is deliberately NOT "seed from today's live batch-walk snapshot"
    (that was this command's original, wrong approach) — for any product
    that already had a return before this fix shipped, today's remaining-
    batch composition is ALREADY skewed by that return, so freezing it would
    permanently lock in the very distortion this feature exists to remove.
    Replaying full history is the only way to recover the number the
    average would show if it had never been able to move except on a
    purchase.

    Idempotent by default: only reconstructs products where avg_unit_cost
    is still 0 (never seeded) — safe to re-run after a partial/interrupted
    run. --force reprocesses every product regardless (only ever needed for
    a genuine redo, e.g. a bug fix in this command itself — never as a
    routine re-run after go-live, since by then avg_unit_cost is correctly
    purchase-driven and replaying history again would ignore everything
    that happened AFTER the previous run).

    Sanity check: after replay, the reconstructed quantity is compared
    against the real Inventory.quantity for that product — a mismatch means
    some quantity-moving event isn't covered by this replay (or a data
    integrity issue predates it) and is reported, never silently ignored;
    avg_unit_cost is still written (it's the best reconstruction available),
    but the mismatch is surfaced for manual review.
    """

    help = "Reconstructs Inventory.avg_unit_cost by replaying full stock history in event order (run once, before any purchase confirms under the new code)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true",
            help="Reprocess every product, even ones with a non-zero avg_unit_cost already. See docstring — not a routine re-run.",
        )

    def handle(self, *args, **options):
        force = options["force"]

        inventories = Inventory.objects.filter(quantity__gt=0)
        if not force:
            inventories = inventories.filter(avg_unit_cost=0)
        inventories = list(inventories)
        product_ids = [inv.product_id for inv in inventories]

        events_by_product = {pid: [] for pid in product_ids}

        # --- Cost events: purchases (the ONLY events that move the average) ---
        purchases = PurchaseItem.objects.filter(
            product_id__in=product_ids, is_deleted=False,
            order__status=PurchaseOrder.Status.CONFIRMED,
            order__confirmed_at__isnull=False,
        ).select_related("order")
        for item in purchases:
            unit_cost = item.total_price / item.quantity if item.quantity else item.unit_price
            events_by_product[item.product_id].append((
                _as_datetime(item.order.confirmed_at), 1, "purchase", item.quantity, unit_cost,
            ))

        # --- Neutral events: quantity only, never the average ---
        sales = InvoiceItem.objects.filter(
            product_id__in=product_ids, invoice__is_deleted=False,
            invoice__confirmed_at__isnull=False,
        ).exclude(invoice__status=Invoice.Status.DRAFT).select_related("invoice")
        for item in sales:
            events_by_product[item.product_id].append((
                _as_datetime(item.invoice.confirmed_at), 0, "sale", -item.quantity, None,
            ))

        purchase_returns = PurchaseReturnItem.objects.filter(
            purchase_item__product_id__in=product_ids,
            return_record__status=PurchaseReturn.Status.ACCEPTED,
            return_record__accepted_at__isnull=False,
        ).select_related("return_record", "purchase_item")
        for ritem in purchase_returns:
            events_by_product[ritem.purchase_item.product_id].append((
                _as_datetime(ritem.return_record.accepted_at), 0, "purchase_return", -ritem.quantity, None,
            ))

        sales_returns = ReturnItem.objects.filter(
            invoice_item__product_id__in=product_ids,
            return_record__status=Return.Status.ACCEPTED,
            return_record__accepted_at__isnull=False,
        ).select_related("return_record", "invoice_item")
        for ritem in sales_returns:
            events_by_product[ritem.invoice_item.product_id].append((
                _as_datetime(ritem.return_record.accepted_at), 0, "sales_return", ritem.quantity, None,
            ))

        lost_items = LostInventoryItem.objects.filter(
            product_id__in=product_ids, record__is_deleted=False,
        ).select_related("record")
        for litem in lost_items:
            events_by_product[litem.product_id].append((
                _as_datetime(litem.record.created_at), 0, "lost", -litem.quantity, None,
            ))

        recoveries = LostInventoryRecovery.objects.filter(
            lost_item__product_id__in=product_ids,
        ).select_related("lost_item")
        for rec in recoveries:
            events_by_product[rec.lost_item.product_id].append((
                _as_datetime(rec.recovered_at), 0, "recovered", rec.quantity, None,
            ))

        seeded = 0
        mismatches = []
        for inv in inventories:
            events = events_by_product.get(inv.product_id, [])
            # Sort by (timestamp, cost-events-last-on-ties) — a same-day
            # purchase applies after same-day neutral events, so a
            # same-day sale/return is reflected in the weight used by that
            # purchase's average update. See _as_datetime's docstring for
            # the DateField-only precision limit this can't fully resolve.
            events.sort(key=lambda e: (e[0], e[1]))

            qty = Decimal("0")
            avg = Decimal("0")
            for _ts, _tiebreak, kind, delta, cost in events:
                if kind == "purchase":
                    batch_qty = Decimal(delta)
                    avg = ((avg * qty) + (cost * batch_qty)) / (qty + batch_qty)
                    qty += batch_qty
                else:
                    qty = max(Decimal("0"), qty + Decimal(delta))

            inv.avg_unit_cost = avg
            inv.save(update_fields=["avg_unit_cost"])
            seeded += 1

            if qty != Decimal(inv.quantity):
                mismatches.append((inv.product_id, qty, inv.quantity))

        self.stdout.write(self.style.SUCCESS(f"Reconstructed avg_unit_cost for {seeded} product(s)."))
        if mismatches:
            self.stdout.write(self.style.WARNING(
                f"{len(mismatches)} product(s) had a replayed quantity that didn't match "
                f"the real Inventory.quantity — avg_unit_cost was still written (best "
                f"available reconstruction), but review these for a missing event source "
                f"or pre-existing data issue: "
                + ", ".join(f"product {pid} (replayed {rq} vs actual {aq})" for pid, rq, aq in mismatches)
            ))
