from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Backfills SupplierLedger, SupplierLedgerEntry, and SupplierLedgerSnapshot "
        "from existing confirmed purchase orders, supplier payments, and purchase returns. "
        "Also auto-generates reference numbers on existing payments and returns that lack them. "
        "Safe to run multiple times — skips already-processed records."
    )

    def handle(self, *args, **kwargs):
        from purchases.models import (
            PurchaseOrder, PurchaseReturn, Supplier, SupplierPayment,
        )
        from ledger.models import SupplierLedger, SupplierLedgerEntry
        from ledger.services import (
            add_advance_entry,
            add_payment_entry,
            add_purchase_entry,
            add_return_entry,
            create_ledger_for_supplier,
            _recalculate_snapshots_from,
        )

        # ----------------------------------------------------------------
        # Step 1: Ensure all suppliers have a ledger
        # ----------------------------------------------------------------
        self.stdout.write("Step 1: Creating missing supplier ledgers...")
        suppliers = Supplier.objects.all()
        for supplier in suppliers:
            ledger, created = SupplierLedger.objects.get_or_create(
                supplier=supplier,
                defaults={
                    "supplier_name": supplier.name,
                    "supplier_code": supplier.code,
                },
            )
            if created:
                self.stdout.write(f"  Created ledger for {supplier.name} ({supplier.code})")

        # ----------------------------------------------------------------
        # Step 2: Backfill reference numbers on existing payments/returns
        # ----------------------------------------------------------------
        self.stdout.write("\nStep 2: Backfilling missing reference numbers...")

        year   = timezone.localtime(timezone.now()).year

        # Supplier payments
        sp_prefix = f"SPY-{year}-"
        sp_last = (
            SupplierPayment.all_objects
            .filter(reference_number__startswith=sp_prefix)
            .order_by("-reference_number")
            .first()
        )
        sp_seq = int(sp_last.reference_number.split("-")[-1]) + 1 if sp_last else 1

        for sp in SupplierPayment.all_objects.filter(reference_number=""):
            sp.reference_number = f"{sp_prefix}{sp_seq:04d}"
            sp.save(update_fields=["reference_number"])
            sp_seq += 1
            self.stdout.write(f"  SPY ref assigned: {sp.reference_number}")

        # Purchase returns
        rtn_prefix = f"RTN-{year}-"
        rtn_last = (
            PurchaseReturn.all_objects
            .filter(reference_number__startswith=rtn_prefix)
            .order_by("-reference_number")
            .first()
        )
        rtn_seq = int(rtn_last.reference_number.split("-")[-1]) + 1 if rtn_last else 1

        for pr in PurchaseReturn.all_objects.filter(reference_number=""):
            pr.reference_number = f"{rtn_prefix}{rtn_seq:04d}"
            pr.save(update_fields=["reference_number"])
            rtn_seq += 1
            self.stdout.write(f"  RTN ref assigned: {pr.reference_number}")

        # ----------------------------------------------------------------
        # Step 3: Backfill billing reference numbers
        # ----------------------------------------------------------------
        self.stdout.write("\nStep 3: Backfilling billing payment/return reference numbers...")
        from billing.models import Payment as BillingPayment, Return as BillingReturn

        pay_prefix = f"PAY-{year}-"
        pay_last = (
            BillingPayment.objects
            .filter(reference_number__startswith=pay_prefix)
            .order_by("-reference_number")
            .first()
        )
        pay_seq = int(pay_last.reference_number.split("-")[-1]) + 1 if pay_last else 1

        for bp in BillingPayment.objects.filter(reference_number=""):
            bp.reference_number = f"{pay_prefix}{pay_seq:04d}"
            bp.save(update_fields=["reference_number"])
            pay_seq += 1
            self.stdout.write(f"  PAY ref assigned: {bp.reference_number}")

        bret_prefix = f"RTN-{year}-"
        bret_last = (
            BillingReturn.objects
            .filter(reference_number__startswith=bret_prefix)
            .order_by("-reference_number")
            .first()
        )
        bret_seq = int(bret_last.reference_number.split("-")[-1]) + 1 if bret_last else 1

        for br in BillingReturn.objects.filter(reference_number=""):
            br.reference_number = f"{bret_prefix}{bret_seq:04d}"
            br.save(update_fields=["reference_number"])
            bret_seq += 1
            self.stdout.write(f"  RTN(billing) ref assigned: {br.reference_number}")

        # ----------------------------------------------------------------
        # Step 4: Create ledger entries from existing transactions
        #         (ordered by date so snapshots are correct)
        # ----------------------------------------------------------------
        self.stdout.write("\nStep 4: Creating ledger entries from existing transactions...")

        # Collect all transactions across all suppliers, sort by date
        transactions = []

        # Confirmed purchase orders → credit entries
        for po in PurchaseOrder.objects.filter(
            is_deleted=False, status="confirmed"
        ).select_related("supplier"):
            if not SupplierLedgerEntry.objects.filter(purchase_order=po).exists():
                transactions.append({
                    "type"    : "purchase",
                    "date"    : timezone.localtime(po.confirmed_at).date() if po.confirmed_at else timezone.localtime(po.created_at).date(),
                    "supplier": po.supplier,
                    "po"      : po,
                })

        # Supplier payments → debit entries
        for sp in SupplierPayment.objects.filter(
            is_deleted=False, amount__gt=0
        ).select_related("order__supplier"):
            if not SupplierLedgerEntry.objects.filter(supplier_payment=sp).exists():
                entry_type = "advance" if sp.note.startswith("Advance payment") else "payment"
                transactions.append({
                    "type"    : entry_type,
                    "date"    : sp.payment_date,
                    "supplier": sp.order.supplier,
                    "sp"      : sp,
                })

        # Accepted purchase returns → debit entries
        for pr in PurchaseReturn.objects.filter(
            is_deleted=False, status="accepted"
        ).select_related("order__supplier"):
            if not SupplierLedgerEntry.objects.filter(purchase_return=pr).exists():
                transactions.append({
                    "type"    : "return",
                    "date"    : timezone.localtime(pr.accepted_at).date() if pr.accepted_at else timezone.localtime(pr.created_at).date(),
                    "supplier": pr.order.supplier,
                    "pr"      : pr,
                })

        # Sort all by date ascending so snapshot cascade is correct
        transactions.sort(key=lambda x: x["date"])

        # Use a system user for backfill (first superuser available)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        system_user = User.objects.filter(is_superuser=True).first()

        for txn in transactions:
            try:
                if txn["type"] == "purchase":
                    add_purchase_entry(
                        supplier=txn["supplier"],
                        purchase_order=txn["po"],
                        amount=txn["po"].net_payable,
                        date=txn["date"],
                        user=system_user,
                    )
                    self.stdout.write(f"  Purchase entry: {txn['po'].order_number}")

                elif txn["type"] == "payment":
                    add_payment_entry(
                        supplier=txn["supplier"],
                        supplier_payment=txn["sp"],
                        amount=txn["sp"].amount,
                        date=txn["date"],
                        user=system_user,
                    )
                    self.stdout.write(f"  Payment entry: {txn['sp'].reference_number}")

                elif txn["type"] == "advance":
                    add_advance_entry(
                        supplier=txn["supplier"],
                        supplier_payment=txn["sp"],
                        amount=txn["sp"].amount,
                        date=txn["date"],
                        user=system_user,
                    )
                    self.stdout.write(f"  Advance entry: {txn['sp'].reference_number}")

                elif txn["type"] == "return":
                    add_return_entry(
                        supplier=txn["supplier"],
                        purchase_return=txn["pr"],
                        amount=txn["pr"].total_return_amount,
                        date=txn["date"],
                        user=system_user,
                    )
                    self.stdout.write(f"  Return entry: {txn['pr'].reference_number}")

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  SKIP (already exists or error): {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nLedger backfill complete. "
            f"{len(transactions)} entries processed."
        ))