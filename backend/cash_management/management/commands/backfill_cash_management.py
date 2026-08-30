from decimal import Decimal

from django.core.management.base import BaseCommand

from cash_management.models import (
    CashAdjustment, CashManagementFlow, Investor, InvestorTransaction,
    InvestorValuationEntry, OwnerTransaction,
)
from cash_management.services import _catch_up_investor_growth


class Command(BaseCommand):
    help = "Backfills the CashManagementFlow singleton and every Investor's stored totals from existing records."

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting CashManagement backfill...\n")

        # Reset singleton — EVERY field this command touches must be reset here.
        # A backfill command must be idempotent (safe to re-run, always lands
        # on the correct absolute value); any field summed further down but
        # left out of this reset silently compounds on every re-run instead.
        cmf, _ = CashManagementFlow.objects.get_or_create(pk=1)
        cmf.total_cash_lost              = Decimal("0")
        cmf.total_cash_recovered         = Decimal("0")
        cmf.total_investor_capital       = Decimal("0")
        cmf.total_investor_withdrawn     = Decimal("0")
        cmf.total_investor_net_worth     = Decimal("0")
        cmf.total_owner_contributions       = Decimal("0")
        cmf.total_owner_drawings            = Decimal("0")
        cmf.total_owner_contributions_count = 0
        cmf.total_owner_withdrawals_count   = 0
        cmf.save()

        # 1. Cash lost/recovered = sum over non-deleted CashAdjustment rows
        for a in CashAdjustment.objects.filter(is_deleted=False):
            if a.adjustment_type == CashAdjustment.AdjustmentType.LOST:
                cmf.total_cash_lost += a.amount
            else:
                cmf.total_cash_recovered += a.amount
        self.stdout.write(f"  total_cash_lost: {cmf.total_cash_lost}")
        self.stdout.write(f"  total_cash_recovered: {cmf.total_cash_recovered}")

        # 2. Investor totals — recompute each investor's stored fields from
        #    scratch (same idempotency discipline as the singleton reset above).
        for investor in Investor.objects.filter(is_deleted=False):
            investor.total_invested = Decimal("0")
            investor.total_withdrawn = Decimal("0")

            # worth_delta is only ever set correctly at live transaction-creation
            # time. Rows created before that logic existed (or restored from an
            # older backup) still carry the field's default of 0, which would
            # silently zero out current_worth and starve growth catch-up (growth
            # is computed FROM current_worth, so a stuck-at-0 worth compounds
            # nothing). Reconstruct worth_delta for every transaction here by
            # replaying them in real chronological order (created_at — the
            # actual order events happened in, not the user-editable
            # transaction_date) and reapplying the exact same rule used live.
            running_worth = Decimal("0")
            running_stake = Decimal("0")
            for t in InvestorTransaction.objects.filter(is_deleted=False, investor=investor).order_by("created_at", "id"):
                if t.transaction_type == InvestorTransaction.TransactionType.INVESTMENT:
                    investor.total_invested += t.amount
                    running_stake += t.amount
                    worth_delta = t.amount
                else:
                    investor.total_withdrawn += t.amount
                    running_stake -= t.amount
                    worth_delta = -running_worth if running_stake == 0 else -t.amount
                running_worth += worth_delta
                if t.worth_delta != worth_delta:
                    t.worth_delta = worth_delta
                    t.save(update_fields=["worth_delta"])
            investor.net_stake = investor.total_invested - investor.total_withdrawn
            investor.save(update_fields=["total_invested", "total_withdrawn", "net_stake"])

            # Growth entries were auto-posted against whatever current_worth was
            # at catch-up time — if that baseline was corrupted by the worth_delta
            # bug above, the posted growth amounts are wrong too. Wipe and let
            # catch-up regenerate them from the now-corrected baseline, at
            # whatever rate is active now — consistent with this app's documented
            # design (backlog months post at the currently active rate).
            InvestorValuationEntry.objects.filter(investor=investor).delete()
            investor.current_worth = running_worth
            investor.save(update_fields=["current_worth"])

            # Catch up any missing growth months, then recompute current_worth
            # from scratch as the sum of every InvestorTransaction.worth_delta
            # (non-deleted) plus every InvestorValuationEntry.amount. This is
            # NOT the same as net_stake + growth_sum — a full-exit withdrawal's
            # worth_delta wipes out prior growth too (see services.py), so
            # worth_delta already captures that wipe exactly. Since current_worth
            # only ever moves by +=worth_delta or +=entry.amount on the live
            # path, summing both is the exact, order-independent replay.
            _catch_up_investor_growth(investor)
            txn_sum = sum(
                (t.worth_delta for t in InvestorTransaction.objects.filter(is_deleted=False, investor=investor)),
                Decimal("0"),
            )
            growth_sum = sum(
                (e.amount for e in InvestorValuationEntry.objects.filter(investor=investor)),
                Decimal("0"),
            )
            investor.current_worth = txn_sum + growth_sum
            investor.save(update_fields=["current_worth"])

            cmf.total_investor_capital   += investor.total_invested
            cmf.total_investor_withdrawn += investor.total_withdrawn
            cmf.total_investor_net_worth += investor.current_worth

        self.stdout.write(f"  total_investor_capital: {cmf.total_investor_capital}")
        self.stdout.write(f"  total_investor_withdrawn: {cmf.total_investor_withdrawn}")
        self.stdout.write(f"  total_investor_net_worth: {cmf.total_investor_net_worth}")

        # 3. Owner totals = sum over non-deleted OwnerTransaction rows
        for t in OwnerTransaction.objects.filter(is_deleted=False):
            if t.transaction_type == OwnerTransaction.TransactionType.CONTRIBUTION:
                cmf.total_owner_contributions += t.amount
                cmf.total_owner_contributions_count += 1
            else:
                cmf.total_owner_drawings += t.amount
                cmf.total_owner_withdrawals_count += 1
        self.stdout.write(f"  total_owner_contributions: {cmf.total_owner_contributions} ({cmf.total_owner_contributions_count} transactions)")
        self.stdout.write(f"  total_owner_drawings: {cmf.total_owner_drawings} ({cmf.total_owner_withdrawals_count} transactions)")

        # Derived fields — same recompute-and-store discipline as the live sync path.
        cmf.net_cash_lost = max(Decimal("0"), cmf.total_cash_lost - cmf.total_cash_recovered)
        cmf.net_investor_capital = cmf.total_investor_capital - cmf.total_investor_withdrawn
        # NOT floored — a sole owner can draw out more than they've deposited.
        cmf.net_owner_capital = cmf.total_owner_contributions - cmf.total_owner_drawings

        cmf.save()
        self.stdout.write(self.style.SUCCESS("\nCashManagement backfill complete."))
        self.stdout.write(f"""
Final CashManagementFlow state:
  total_cash_lost               : {cmf.total_cash_lost}
  total_cash_recovered          : {cmf.total_cash_recovered}
  net_cash_lost                  : {cmf.net_cash_lost}
  total_investor_capital        : {cmf.total_investor_capital}
  total_investor_withdrawn      : {cmf.total_investor_withdrawn}
  net_investor_capital           : {cmf.net_investor_capital}
  total_investor_net_worth       : {cmf.total_investor_net_worth}
  total_owner_contributions       : {cmf.total_owner_contributions}
  total_owner_drawings            : {cmf.total_owner_drawings}
  total_owner_contributions_count : {cmf.total_owner_contributions_count}
  total_owner_withdrawals_count   : {cmf.total_owner_withdrawals_count}
  net_owner_capital                : {cmf.net_owner_capital}
""")
