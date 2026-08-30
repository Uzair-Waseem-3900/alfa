from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Backfills CustomerLedger, CustomerLedgerEntry, and CustomerLedgerSnapshot "
        "from existing confirmed invoices, payments, and accepted returns. "
        "Every entry is dated using the transaction's REAL date (confirmed_at / "
        "payment_date / accepted_at) — never the date this command happens to run "
        "on — so historical snapshots and running balances stay correct against "
        "real (including production) data. "
        "Safe to run multiple times — skips already-processed records."
    )

    def handle(self, *args, **kwargs):
        from billing.models import Customer, Invoice, Payment, Return
        from ledger.models import CustomerLedger, CustomerLedgerEntry
        from ledger.services import (
            add_customer_advance_entry,
            add_customer_opening_balance_entry,
            add_customer_payment_entry,
            add_customer_return_entry,
            add_sale_entry,
        )

        # ----------------------------------------------------------------
        # Step 1: Ensure all customers have a ledger
        # ----------------------------------------------------------------
        self.stdout.write("Step 1: Creating missing customer ledgers...")
        for customer in Customer.objects.all():
            ledger, created = CustomerLedger.objects.get_or_create(
                customer=customer,
                defaults={
                    "customer_name": customer.name,
                    "customer_code": customer.code,
                },
            )
            if created:
                self.stdout.write(f"  Created ledger for {customer.name} ({customer.code})")

        # ----------------------------------------------------------------
        # Step 2: Collect all transactions across all customers, sorted by
        #         their REAL transaction date (not created_at, not "today")
        #         so snapshots cascade correctly against real history.
        # ----------------------------------------------------------------
        self.stdout.write("\nStep 2: Collecting existing transactions...")

        transactions = []

        # Confirmed invoices (incl. data-entry opening-balance invoices,
        # handled separately below via the opening_balance entry_type) →
        # debit (sale) entries. Opening-balance invoices are excluded here —
        # they're backfilled as opening_balance entries, not sale entries.
        for invoice in Invoice.objects.filter(
            is_deleted=False, status__in=["confirmed", "partial", "returned"], is_data_entry=False,
        ).select_related("customer"):
            if not CustomerLedgerEntry.objects.filter(invoice=invoice, entry_type="sale").exists():
                transactions.append({
                    "type"    : "sale",
                    "date"    : timezone.localtime(invoice.confirmed_at).date() if invoice.confirmed_at else timezone.localtime(invoice.created_at).date(),
                    "customer": invoice.customer,
                    "invoice" : invoice,
                })

        # Data-entry opening-balance invoices → opening_balance debit entries
        for invoice in Invoice.objects.filter(
            is_deleted=False, is_data_entry=True,
        ).select_related("customer"):
            if not CustomerLedgerEntry.objects.filter(invoice=invoice, entry_type="opening_balance").exists():
                transactions.append({
                    "type"    : "opening_balance",
                    "date"    : timezone.localtime(invoice.confirmed_at).date() if invoice.confirmed_at else timezone.localtime(invoice.created_at).date(),
                    "customer": invoice.customer,
                    "invoice" : invoice,
                })

        # Payments (positive amount only — the negative credit-note payment
        # created by accept_return is intentionally tracked via the Return
        # below, not here, to avoid double counting) → payment/advance
        # credit entries, split the same way create_invoice/create_payment
        # split them at write time (by note prefix).
        for payment in Payment.objects.filter(
            is_deleted=False, amount__gt=0,
        ).select_related("invoice__customer"):
            if not CustomerLedgerEntry.objects.filter(payment=payment).exists():
                entry_type = "advance" if payment.note.startswith("Advance payment") else "payment"
                transactions.append({
                    "type"    : entry_type,
                    "date"    : payment.payment_date,
                    "customer": payment.invoice.customer,
                    "payment" : payment,
                })

        # Accepted returns → return credit entries
        for ret in Return.objects.filter(
            is_deleted=False, status="accepted",
        ).select_related("invoice__customer"):
            if not CustomerLedgerEntry.objects.filter(customer_return=ret).exists():
                transactions.append({
                    "type"    : "return",
                    "date"    : timezone.localtime(ret.accepted_at).date() if ret.accepted_at else timezone.localtime(ret.created_at).date(),
                    "customer": ret.invoice.customer,
                    "return"  : ret,
                })

        # Sort all by real transaction date ascending so the snapshot
        # cascade is correct — this is the whole point of using
        # confirmed_at/payment_date/accepted_at above instead of created_at
        # or "now": production data must land on the date it actually
        # happened, not the date this command happens to run.
        transactions.sort(key=lambda x: x["date"])

        from django.contrib.auth import get_user_model
        User = get_user_model()
        system_user = User.objects.filter(is_superuser=True).first()

        self.stdout.write(f"\nStep 3: Replaying {len(transactions)} transactions in date order...")

        for txn in transactions:
            try:
                if txn["type"] == "sale":
                    add_sale_entry(
                        customer=txn["customer"],
                        invoice=txn["invoice"],
                        amount=txn["invoice"].grand_total,
                        date=txn["date"],
                        user=system_user,
                    )
                    self.stdout.write(f"  Sale entry: {txn['invoice'].bill_number}")

                elif txn["type"] == "opening_balance":
                    add_customer_opening_balance_entry(
                        customer=txn["customer"],
                        invoice=txn["invoice"],
                        amount=txn["invoice"].grand_total,
                        date=txn["date"],
                        reference=f"OB-{txn['customer'].code}",
                        user=system_user,
                    )
                    self.stdout.write(f"  Opening balance entry: {txn['invoice'].bill_number}")

                elif txn["type"] == "payment":
                    add_customer_payment_entry(
                        customer=txn["customer"],
                        payment=txn["payment"],
                        amount=txn["payment"].amount,
                        date=txn["date"],
                        user=system_user,
                    )
                    self.stdout.write(f"  Payment entry: {txn['payment'].reference_number}")

                elif txn["type"] == "advance":
                    add_customer_advance_entry(
                        customer=txn["customer"],
                        payment=txn["payment"],
                        amount=txn["payment"].amount,
                        date=txn["date"],
                        user=system_user,
                    )
                    self.stdout.write(f"  Advance entry: {txn['payment'].reference_number}")

                elif txn["type"] == "return":
                    add_customer_return_entry(
                        customer=txn["customer"],
                        customer_return=txn["return"],
                        amount=txn["return"].total_return_amount,
                        date=txn["date"],
                        user=system_user,
                    )
                    self.stdout.write(f"  Return entry: {txn['return'].reference_number}")

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  SKIP (already exists or error): {e}"))

        self.stdout.write(self.style.SUCCESS(
            f"\nCustomer ledger backfill complete. "
            f"{len(transactions)} entries processed."
        ))
