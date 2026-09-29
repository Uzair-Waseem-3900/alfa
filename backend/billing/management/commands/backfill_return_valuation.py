from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone

CHUNK = 500


class Command(BaseCommand):
    help = (
        "Re-values accepted customer returns at the price actually billed "
        "(effective_price x qty, no tax) instead of the list price, and "
        "repairs every stored copy of that amount: ReturnItem/Return totals, "
        "the auto credit-note Payment, the customer ledger return entry (and "
        "its monthly snapshots), the invoice payment summary, the CashFlow "
        "returns counters and the credit score. Pending returns get their "
        "display snapshots refreshed. DRY-RUN by default; idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Write the changes (default is a read-only dry run).")
        parser.add_argument("--confirm-db", default="",
                            help="Required with --apply: must equal the name@host confirm-token printed at the top.")
        parser.add_argument("--user-email", default="",
                            help="Required with --apply: user recorded as updated_by.")
        parser.add_argument("--return-ref", default="",
                            help="Limit to one return (e.g. RTN-2026-0012). CashFlow is then adjusted "
                                 "by that return's change only, not the global residual.")

    # ------------------------------------------------------------------ #
    def handle(self, *args, **opts):
        from billing.models import Return

        db = connection.settings_dict
        # name@host, not just the name: a production and a dev Postgres can
        # share a name (e.g. "postgres") but not a host.
        db_token = f"{Path(str(db['NAME'])).name}@{db.get('HOST') or 'local'}"
        self.stdout.write(f"Target database: engine={connection.vendor} confirm-token={db_token}")
        apply_changes = opts["apply"]
        user = None
        if apply_changes:
            if opts["confirm_db"] != db_token:
                raise CommandError(f"--apply needs --confirm-db {db_token} (the database printed above).")
            from users.models import User
            user = User.objects.filter(email=opts["user_email"]).first()
            if not user:
                raise CommandError("--apply needs --user-email of an existing user.")
        self.stdout.write("MODE: " + ("APPLY" if apply_changes else "DRY RUN (nothing is written)") + "\n")

        base = Return.objects.filter(status=Return.Status.ACCEPTED)
        pending = Return.objects.filter(status=Return.Status.PENDING)
        if opts["return_ref"]:
            base = base.filter(reference_number=opts["return_ref"])
            pending = pending.filter(reference_number=opts["return_ref"])

        plan = self._build_plan(list(base.order_by("accepted_at", "id").values_list("id", flat=True)))
        pending_items = self._pending_item_fixes(list(pending.values_list("id", flat=True)))
        self._report(plan, pending_items, scoped=bool(opts["return_ref"]))

        if not apply_changes:
            self.stdout.write("\nDry run only. Re-run with --apply --confirm-db <name> --user-email <email> to write.")
            return

        with transaction.atomic():
            self._apply(plan, pending_items, user, scoped=bool(opts["return_ref"]))
        self.stdout.write(self.style.SUCCESS("\nDone. Re-run (dry run) to confirm nothing is left to fix."))

    # ------------------------------------------------------------------ #
    def _build_plan(self, return_ids):
        from billing.models import Payment, Return, ReturnItem
        from billing.services import RETURN_CREDIT_NOTE_PREFIX
        from billing.utils import calculate_return_line_total
        from ledger.models import CustomerLedgerEntry

        plan = {
            "returns": [],        # (Return, old_total, new_total)
            "item_fixes": [],     # (ReturnItem, new_selling_price, new_line_total)
            "payment_fixes": [],  # (Payment, new_amount)
            "ledger_fixes": [],   # (CustomerLedgerEntry, new_credit)
            "anomalies": [],
            "affected": {},       # return_id -> Return (anything differing)
        }
        for i in range(0, len(return_ids), CHUNK):
            chunk = list(
                Return.objects.filter(pk__in=return_ids[i:i + CHUNK])
                .select_related("invoice__customer").order_by("accepted_at", "id")
            )
            items_by_return = {}
            for ri in ReturnItem.objects.filter(return_record_id__in=[r.id for r in chunk]).select_related("invoice_item"):
                items_by_return.setdefault(ri.return_record_id, []).append(ri)
            # Look payments up through the indexed invoice FK (Payment.note is
            # not indexed) and match the credit-note text in Python.
            wanted = {f"{RETURN_CREDIT_NOTE_PREFIX}{r.reference_number}" for r in chunk}
            payments = {}
            for p in Payment.objects.filter(
                invoice_id__in={r.invoice_id for r in chunk}, amount__lt=0, is_deleted=False,
            ):
                if p.note in wanted:
                    payments.setdefault(p.note, []).append(p)
            entries = {}
            for e in CustomerLedgerEntry.objects.filter(
                customer_return_id__in=[r.id for r in chunk],
                entry_type=CustomerLedgerEntry.EntryType.RETURN,
            ):
                entries.setdefault(e.customer_return_id, []).append(e)

            for r in chunk:
                new_total = Decimal("0")
                differs = False
                for ri in items_by_return.get(r.id, []):
                    price = ri.invoice_item.effective_price
                    line = calculate_return_line_total(effective_price=price, quantity=ri.quantity)
                    new_total += line
                    if ri.selling_price != price or ri.line_total != line:
                        plan["item_fixes"].append((ri, price, line))
                        differs = True
                if r.total_return_amount != new_total:
                    plan["returns"].append((r, r.total_return_amount, new_total))
                    differs = True

                pays = payments.get(f"{RETURN_CREDIT_NOTE_PREFIX}{r.reference_number}", [])
                if len(pays) == 1:
                    if pays[0].amount != -new_total:
                        plan["payment_fixes"].append((pays[0], -new_total))
                        differs = True
                else:
                    plan["anomalies"].append(f"{r.reference_number}: {len(pays)} credit-note payments found (expected 1) - skipped")

                ents = entries.get(r.id, [])
                if len(ents) == 1:
                    if ents[0].credit != new_total:
                        plan["ledger_fixes"].append((ents[0], new_total))
                        differs = True
                else:
                    plan["anomalies"].append(
                        f"{r.reference_number}: {len(ents)} ledger return entries found (expected 1) - skipped "
                        f"(use backfill_customer_ledger for a missing one)"
                    )
                if differs:
                    plan["affected"][r.id] = r
        return plan

    def _pending_item_fixes(self, return_ids):
        from billing.models import ReturnItem
        from billing.utils import calculate_return_line_total

        fixes = []
        for i in range(0, len(return_ids), CHUNK):
            for ri in ReturnItem.objects.filter(return_record_id__in=return_ids[i:i + CHUNK]).select_related("invoice_item"):
                price = ri.invoice_item.effective_price
                line = calculate_return_line_total(effective_price=price, quantity=ri.quantity)
                if ri.selling_price != price or ri.line_total != line:
                    fixes.append((ri, price, line))
        return fixes

    # ------------------------------------------------------------------ #
    def _ledger_balances(self, ledger_ids):
        from ledger.models import CustomerLedgerEntry

        out = {}
        for i in range(0, len(ledger_ids), CHUNK):
            rows = (CustomerLedgerEntry.objects.filter(ledger_id__in=ledger_ids[i:i + CHUNK])
                    .values("ledger_id").annotate(d=Sum("debit"), c=Sum("credit")))
            for row in rows:
                out[row["ledger_id"]] = (row["d"] or Decimal("0")) - (row["c"] or Decimal("0"))
        return out

    def _cashflow_residual(self, plan, scoped, applied=False):
        """
        How much total_customer_returns_value must move. Unscoped: the gap
        between the sum of accepted return totals (after the planned
        re-valuation) and the stored counter - the same definition
        backfill_cashflow uses. Scoped (--return-ref): just that return's
        planned change. `applied=True` once the new totals are already in the DB.
        """
        from cash_flow.models import CashFlow
        from billing.models import Return

        cf = CashFlow.objects.get_or_create(pk=1)[0]
        planned = sum((new - old for _, old, new in plan["returns"]), Decimal("0"))
        if scoped:
            return planned, cf
        stored = Return.objects.filter(status=Return.Status.ACCEPTED).aggregate(s=Sum("total_return_amount"))["s"] or Decimal("0")
        expected = stored if applied else stored + planned
        return expected - cf.total_customer_returns_value, cf

    def _report(self, plan, pending_items, scoped):
        w = self.stdout.write
        w(f"Accepted returns needing a fix: {len(plan['affected'])}")
        for r in plan["affected"].values():
            change = next(((o, n) for rr, o, n in plan["returns"] if rr.id == r.id), None)
            w(f"  {r.reference_number} ({r.invoice.bill_number}): " +
              (f"total {change[0]} -> {change[1]}" if change else "total already correct (dependent copies differ)"))
        w(f"  return items to fix: {len(plan['item_fixes'])} | credit-note payments: {len(plan['payment_fixes'])} "
          f"| ledger return entries: {len(plan['ledger_fixes'])}")

        ledger_ids = sorted({e.ledger_id for e, _ in plan["ledger_fixes"]})
        before = self._ledger_balances(ledger_ids)
        shift = {}
        for e, new in plan["ledger_fixes"]:
            shift[e.ledger_id] = shift.get(e.ledger_id, Decimal("0")) + (e.credit - new)
        for lid in ledger_ids:
            w(f"  ledger {lid}: balance owed {before.get(lid, Decimal('0'))} -> {before.get(lid, Decimal('0')) + shift[lid]}")

        residual, cf = self._cashflow_residual(plan, scoped)
        w(f"CashFlow: returns_value {cf.total_customer_returns_value}, customer_outstanding {cf.customer_outstanding}; "
          f"residual to apply {residual} (returns_value += residual, customer_outstanding -= residual)")
        w(f"Pending returns whose display snapshot will be refreshed: {len(pending_items)}")
        for a in plan["anomalies"]:
            w(self.style.WARNING(f"ANOMALY {a}"))

    # ------------------------------------------------------------------ #
    def _apply(self, plan, pending_items, user, scoped):
        from billing.models import Payment, Return, ReturnItem
        from billing.services import _sync_invoice_payment_summary
        from cash_flow.models import CashFlow
        from cash_flow.services import sync_customer_returns_value_corrected
        from credit_score.services import recalculate_credit_score
        from ledger.models import CustomerLedgerSnapshot
        from ledger.services import refresh_customer_return_entries

        now = timezone.now()

        items = []
        for ri, price, line in plan["item_fixes"] + pending_items:
            ri.selling_price, ri.line_total = price, line
            items.append(ri)
        ReturnItem.objects.bulk_update(items, ["selling_price", "line_total"], batch_size=CHUNK)

        rets = []
        for r, _old, new in plan["returns"]:
            r.total_return_amount, r.updated_by, r.updated_at = new, user, now
            rets.append(r)
        Return.objects.bulk_update(rets, ["total_return_amount", "updated_by", "updated_at"], batch_size=CHUNK)

        pays = []
        for p, new in plan["payment_fixes"]:
            p.amount, p.updated_by, p.updated_at = new, user, now
            pays.append(p)
        Payment.objects.bulk_update(pays, ["amount", "updated_by", "updated_at"], batch_size=CHUNK)

        # Lock order mirrors the live accept_return (customer -> CashFlow ->
        # ledger -> credit score) so a concurrent accept can't deadlock with
        # this repair.
        # 1. Invoice summary (also nudges the sales man's outstanding counter
        #    by the change in credit_outstanding), once per affected invoice.
        for inv in sorted({r.invoice for r in plan["affected"].values()}, key=lambda i: i.pk):
            inv.refresh_from_db()
            _sync_invoice_payment_summary(inv)

        # 2. CashFlow returns counters.
        CashFlow.objects.select_for_update().get_or_create(pk=1)
        residual, _cf = self._cashflow_residual(plan, scoped, applied=True)
        if residual:
            sync_customer_returns_value_corrected(delta=residual, user=user)

        # 3. Customer ledger return entries + monthly snapshots.
        by_ledger = {}
        for e, new in plan["ledger_fixes"]:
            by_ledger.setdefault(e.ledger_id, {})[e.pk] = new
        for lid in sorted(by_ledger):
            refresh_customer_return_entries(ledger_id=lid, amounts_by_entry_id=by_ledger[lid])

        # 4. Credit score.
        for cid in sorted({r.invoice.customer_id for r in plan["affected"].values()}):
            recalculate_credit_score(
                customer_id=cid, user=user, trigger="return_valuation_repair",
            )

        # Verification: each touched ledger's latest snapshot must equal
        # sum(debit) - sum(credit) over all its entries.
        balances = self._ledger_balances(sorted(by_ledger))
        for lid, expected in balances.items():
            snap = CustomerLedgerSnapshot.objects.filter(ledger_id=lid).order_by("-year_month").first()
            if snap is None or snap.closing_balance != expected:
                raise CommandError(
                    f"Ledger {lid}: latest snapshot {snap and snap.closing_balance} != entries balance {expected}. Rolled back."
                )
