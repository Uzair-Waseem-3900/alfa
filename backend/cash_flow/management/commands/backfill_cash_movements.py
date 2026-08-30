from django.core.management.base import BaseCommand
from django.db import transaction

from cash_flow.models import CashMovement
from cash_flow.services import _movement_payload, _source_label


class Command(BaseCommand):
    help = (
        "Rebuilds the CashMovement event table from the 14 source models. "
        "Idempotent — wipes and reconstructs, so it is also the repair tool "
        "if the event table ever drifts from the sources."
    )

    def _record(self, batch, source):
        payload = _movement_payload(source)
        if payload is None:
            return
        batch.append(CashMovement(
            source_model=_source_label(source), source_id=source.pk, **payload,
        ))

    @transaction.atomic
    def handle(self, *args, **kwargs):
        from billing.models import Payment
        from purchases.models import SupplierPayment
        from cash_flow.models import Expense

        self.stdout.write("Rebuilding CashMovement events from source tables...\n")

        deleted, _ = CashMovement.objects.all().delete()
        self.stdout.write(f"  wiped {deleted} existing event rows")

        batch = []

        # Each block mirrors get_cash_in_hand_breakdown_from_sources()'s
        # source set exactly; the per-row skip rules (amount<=0, non-'new'
        # assets, scrapped disposals, draft-invoice payments) live in the
        # shared payload builders, so live writes and this backfill can
        # never disagree. Optional apps import defensively, same as the
        # selector.

        try:
            from data_entry.models import OpeningCashEntry
            for e in OpeningCashEntry.objects.all():
                self._record(batch, e)
        except Exception:
            pass

        for p in Payment.objects.filter(is_deleted=False).select_related("invoice__customer"):
            self._record(batch, p)

        for e in Expense.objects.filter(is_deleted=False).select_related("category"):
            self._record(batch, e)

        for p in SupplierPayment.objects.filter(is_deleted=False).select_related("order__supplier"):
            self._record(batch, p)

        try:
            from taxes.models import TaxPayment, WHTPayment
            for tp in TaxPayment.objects.filter(is_deleted=False):
                self._record(batch, tp)
            for wp in WHTPayment.objects.filter(is_deleted=False):
                self._record(batch, wp)
        except Exception:
            pass

        try:
            from profits.models import InvestorProfitPayout, OwnerProfitPayout
            for pp in InvestorProfitPayout.objects.filter(is_deleted=False).select_related("share__monthly_profit"):
                self._record(batch, pp)
            for op in OwnerProfitPayout.objects.filter(is_deleted=False).select_related("owner_share__monthly_profit"):
                self._record(batch, op)
        except Exception:
            pass

        try:
            from cash_management.models import CashAdjustment, InvestorTransaction, OwnerTransaction
            for a in CashAdjustment.objects.filter(is_deleted=False):
                self._record(batch, a)
            for t in InvestorTransaction.objects.filter(is_deleted=False).select_related("investor"):
                self._record(batch, t)
            for t in OwnerTransaction.objects.filter(is_deleted=False):
                self._record(batch, t)
        except Exception:
            pass

        try:
            from assets.models import Asset, AssetDisposal
            for a in Asset.objects.filter(is_deleted=False):
                self._record(batch, a)
            for d in AssetDisposal.objects.all().select_related("asset"):
                self._record(batch, d)
        except Exception:
            pass

        try:
            from recurring_expenses.models import RecurringExpenseAssignmentPayment
            for p in RecurringExpenseAssignmentPayment.objects.filter(is_deleted=False).select_related("assignment"):
                self._record(batch, p)
        except Exception:
            pass

        CashMovement.objects.bulk_create(batch, batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"\nCashMovement backfill complete — {len(batch)} events created."
        ))
