from django.core.management.base import BaseCommand
from django.db import transaction

from billing.models import Payment
from cash_flow.models import CashMovement
from purchases.models import SupplierPayment


class Command(BaseCommand):
    """
    One-time relabel: the system runs on cash only for now (JazzCash/
    Easypaisa/Bank Transfer aren't actually tracked as separate accounts
    yet), so every existing payment method — and every CashMovement row,
    including the ones that never had a method (expenses, tax payments,
    etc.) — gets set to "cash". Purely a display label; `method` is never
    branched on anywhere in the business logic, so this cannot change any
    balance, total, or the balance-sheet invariant.

    Safe to re-run: idempotent, only ever moves rows toward "cash".
    """

    help = "Relabels every Payment/SupplierPayment/CashMovement method to 'cash'."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show how many rows would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        payments_qs = Payment.objects.exclude(method=Payment.Method.CASH)
        supplier_payments_qs = SupplierPayment.objects.exclude(method=SupplierPayment.Method.CASH)
        movements_qs = CashMovement.objects.exclude(method="cash")

        payments_count = payments_qs.count()
        supplier_payments_count = supplier_payments_qs.count()
        movements_count = movements_qs.count()

        self.stdout.write(f"billing.Payment rows to update           : {payments_count}")
        self.stdout.write(f"purchases.SupplierPayment rows to update : {supplier_payments_count}")
        self.stdout.write(f"cash_flow.CashMovement rows to update    : {movements_count}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run — no changes written."))
            return

        with transaction.atomic():
            payments_updated = payments_qs.update(method=Payment.Method.CASH)
            supplier_payments_updated = supplier_payments_qs.update(method=SupplierPayment.Method.CASH)
            movements_updated = movements_qs.update(method="cash")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Updated {payments_updated} payments, "
            f"{supplier_payments_updated} supplier payments, "
            f"{movements_updated} cash movements."
        ))
