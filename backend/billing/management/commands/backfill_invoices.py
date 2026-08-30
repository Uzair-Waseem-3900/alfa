from decimal import Decimal

from django.core.management.base import BaseCommand

from billing.models import Invoice, Payment
from billing.utils import calculate_invoice_totals, calculate_line_item


class Command(BaseCommand):
    help = "Backfill grand_total, credit_outstanding, and payment tracking on existing confirmed invoices."

    def handle(self, *args, **kwargs):
        invoices = Invoice.objects.filter(is_deleted=False).exclude(status="draft")
        total = invoices.count()
        self.stdout.write(f"Found {total} invoices to backfill...\n")

        for invoice in invoices:
            # Step 1: Recalculate totals from line items
            line_data = []
            for item in invoice.items.all():
                calc = calculate_line_item(
                    quantity=item.quantity,
                    selling_price=item.selling_price,
                    discount=item.discount,
                    gst=item.gst,
                    wht=item.wht,
                )
                calc["line_cogs"] = item.line_cogs
                line_data.append(calc)

            if line_data:
                totals = calculate_invoice_totals(line_data)
                invoice.subtotal     = totals["subtotal"]
                invoice.gst_total    = totals["gst_total"]
                invoice.wht_total    = totals["wht_total"]
                invoice.grand_total  = totals["grand_total"]
                invoice.total_cogs   = totals["total_cogs"]
                invoice.gross_profit = totals["gross_profit"]
                invoice.save(update_fields=[
                    "subtotal", "gst_total", "wht_total", "grand_total",
                    "total_cogs", "gross_profit",
                ])

            # Step 2: Recalculate payment tracking from actual payments
            payments = Payment.objects.filter(invoice=invoice, is_deleted=False)
            cash_received  = Decimal("0")
            return_credits = Decimal("0")

            for p in payments:
                if p.amount > 0:
                    cash_received += p.amount
                else:
                    return_credits += abs(p.amount)

            invoice.refresh_from_db(fields=["grand_total"])
            credit_outstanding = max(
                Decimal("0"),
                invoice.grand_total - cash_received - return_credits,
            )
            remaining_amount = credit_outstanding
            total_paid       = cash_received

            if remaining_amount <= 0:
                payment_status = "paid"
            elif cash_received > 0 or return_credits > 0:
                payment_status = "partial"
            else:
                payment_status = "unpaid"

            invoice.cash_received      = cash_received
            invoice.credit_outstanding = credit_outstanding
            invoice.total_paid         = total_paid
            invoice.remaining_amount   = remaining_amount
            invoice.payment_status     = payment_status
            invoice.save(update_fields=[
                "cash_received", "credit_outstanding", "total_paid",
                "remaining_amount", "payment_status",
            ])

            self.stdout.write(
                f"  {invoice.bill_number}: "
                f"grand_total={invoice.grand_total}, "
                f"credit_outstanding={invoice.credit_outstanding}, "
                f"payment_status={invoice.payment_status}"
            )

        self.stdout.write(self.style.SUCCESS(f"\nBackfill complete. {total} invoices updated."))