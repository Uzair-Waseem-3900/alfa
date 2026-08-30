from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce


class Command(BaseCommand):
    """
    One-off repair for the accept_purchase_return bug fixed 2026-08-09:
    remaining_quantity used to INCREASE on an accepted purchase return
    instead of decreasing, silently diverging every affected batch's
    remaining_quantity from the true physical stock (Inventory.quantity
    tracked correctly the whole time, since sync_inventory itself was never
    buggy).

    Recomputes the CORRECT remaining_quantity for every confirmed,
    non-deleted PurchaseItem from source ledgers only — never from the
    (possibly drifted) remaining_quantity field itself:

        correct = quantity
                  - returned_quantity                     (purchase returns to supplier)
                  - net FIFOLedger.quantity for this batch (billing sales, net of customer-return reversals)
                  - net unrecovered LostInventoryFIFOConsumption for this batch

    For each PRODUCT, sums the correct remaining_quantity across all its
    batches and compares to Inventory.quantity (the trusted, never-buggy
    aggregate). Only products where the sums MATCH get their batches
    corrected — a mismatch means something else needs manual investigation
    first, so those are reported and left untouched rather than guessed at.

    Defaults to a dry run (report only). Pass --apply to actually write the
    corrected remaining_quantity values.
    """
    help = "Repairs PurchaseItem.remaining_quantity drift caused by the pre-fix accept_purchase_return bug."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Write the corrected remaining_quantity values. Without this flag, only reports what would change.",
        )

    def handle(self, *args, **options):
        from purchases.models import Inventory, LostInventoryFIFOConsumption, PurchaseItem, PurchaseOrder
        from billing.models import FIFOLedger

        apply_changes = options["apply"]
        zero = 0

        batches = list(
            PurchaseItem.objects.filter(
                is_deleted=False, order__status=PurchaseOrder.Status.CONFIRMED,
            ).select_related("product", "order")
        )
        if not batches:
            self.stdout.write("No confirmed purchase items found — nothing to reconcile.")
            return

        # Net sold per batch — FIFOLedger.quantity is signed (positive =
        # consumed by a sale, negative = restored by a customer return), so
        # a plain sum already nets the two out.
        net_sold_by_batch = dict(
            FIFOLedger.objects.filter(purchase_id__in=[b.id for b in batches])
            .values("purchase_id").annotate(total=Coalesce(Sum("quantity"), zero))
            .values_list("purchase_id", "total")
        )

        # Net unrecovered lost quantity per batch — quantity originally
        # drawn from this batch when marked lost, minus whatever's since
        # been restored via "mark as found".
        lost_rows = (
            LostInventoryFIFOConsumption.objects
            .filter(purchase_item_id__in=[b.id for b in batches])
            .values("purchase_item_id")
            .annotate(
                drawn=Coalesce(Sum("quantity"), zero),
                restored=Coalesce(Sum("restored_quantity"), zero),
            )
        )
        net_lost_by_batch = {row["purchase_item_id"]: row["drawn"] - row["restored"] for row in lost_rows}

        inventory_by_product = dict(
            Inventory.objects.values_list("product_id", "quantity")
        )

        batches_by_product = {}
        for batch in batches:
            batches_by_product.setdefault(batch.product_id, []).append(batch)

        products_matched = 0
        products_flagged = []
        batches_corrected = 0
        batches_already_correct = 0

        for product_id, product_batches in batches_by_product.items():
            corrected = {}
            total_correct = 0
            for batch in product_batches:
                net_sold = net_sold_by_batch.get(batch.id, 0)
                net_lost = net_lost_by_batch.get(batch.id, 0)
                correct_remaining = batch.quantity - batch.returned_quantity - net_sold - net_lost
                corrected[batch.id] = correct_remaining
                total_correct += correct_remaining

            actual_inventory = inventory_by_product.get(product_id, 0)

            if total_correct != actual_inventory:
                product_name = product_batches[0].product.name
                products_flagged.append({
                    "product_id": product_id,
                    "product_name": product_name,
                    "computed_total": total_correct,
                    "inventory_quantity": actual_inventory,
                })
                continue

            products_matched += 1
            for batch in product_batches:
                if batch.remaining_quantity != corrected[batch.id]:
                    batches_corrected += 1
                    if apply_changes:
                        with transaction.atomic():
                            PurchaseItem.objects.filter(pk=batch.pk).update(
                                remaining_quantity=corrected[batch.id],
                            )
                    self.stdout.write(
                        f"  {'FIXED' if apply_changes else 'WOULD FIX'}: "
                        f"{batch.order.order_number} / {batch.product.name} "
                        f"(item #{batch.id}): remaining_quantity {batch.remaining_quantity} -> {corrected[batch.id]}"
                    )
                else:
                    batches_already_correct += 1

        self.stdout.write("")
        self.stdout.write(f"Products checked: {len(batches_by_product)}")
        self.stdout.write(f"Products reconciled cleanly: {products_matched}")
        self.stdout.write(f"Batches already correct: {batches_already_correct}")
        self.stdout.write(f"Batches {'corrected' if apply_changes else 'needing correction'}: {batches_corrected}")

        if products_flagged:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                f"{len(products_flagged)} product(s) FLAGGED for manual review "
                f"(computed batch total does not match Inventory.quantity — "
                f"do not auto-fix, something else needs investigation first):"
            ))
            for p in products_flagged:
                self.stdout.write(
                    f"  - {p['product_name']} (id={p['product_id']}): "
                    f"computed remaining total={p['computed_total']}, "
                    f"Inventory.quantity={p['inventory_quantity']}"
                )

        if not apply_changes and batches_corrected:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "Dry run only — re-run with --apply to write these corrections."
            ))
        elif apply_changes:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Reconciliation applied."))
