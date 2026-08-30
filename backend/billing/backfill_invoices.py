"""
One-time backfill script for invoices confirmed before grand_total,
credit_outstanding, and payment tracking fields were added.

Run via:
    python manage.py shell < billing/backfill_invoices.py

OR paste into shell:
    python manage.py shell
    >>> exec(open('billing/backfill_invoices.py').read())
"""

from billing.models import Invoice
from billing.services import _recalculate_invoice_totals, _sync_invoice_payment_summary

confirmed = Invoice.objects.filter(
    status__in=["confirmed", "partial", "returned"],
    is_deleted=False,
).exclude(
    grand_total__gt=0,  # skip already-correct records
)

print(f"Found {confirmed.count()} invoices to backfill...")

for invoice in confirmed:
    try:
        # Recalculate totals from line items
        _recalculate_invoice_totals(invoice)

        # Re-sync payment summary (sets credit_outstanding = grand_total initially,
        # then subtracts any existing payments)
        invoice.refresh_from_db()
        if invoice.grand_total > 0 and invoice.credit_outstanding == 0:
            invoice.credit_outstanding = invoice.grand_total
            invoice.remaining_amount   = invoice.grand_total
            invoice.save(update_fields=["credit_outstanding", "remaining_amount"])

        # Re-sync payments to correctly reduce credit_outstanding
        _sync_invoice_payment_summary(invoice)

        print(f"  Fixed {invoice.bill_number}: grand_total={invoice.grand_total}, "
              f"credit_outstanding={invoice.credit_outstanding}")
    except Exception as e:
        print(f"  ERROR on {invoice.bill_number}: {e}")

print("Backfill complete.")