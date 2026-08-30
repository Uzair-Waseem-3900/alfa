from decimal import Decimal

from django.core.management.base import BaseCommand

from taxes.models import TaxFlow


class Command(BaseCommand):
    help = "Backfills the TaxFlow singleton from existing confirmed purchases, invoices, and tax payments."

    def handle(self, *args, **kwargs):
        from billing.models import Invoice
        from purchases.models import PurchaseOrder
        from taxes.models import TaxPayment, WHTPayment

        self.stdout.write("Starting TaxFlow backfill...\n")

        # Reset singleton — EVERY field this command touches must be reset here.
        # A backfill command must be idempotent (safe to re-run, always lands
        # on the correct absolute value); any field summed further down but
        # left out of this reset silently compounds on every re-run instead.
        tf, _ = TaxFlow.objects.get_or_create(pk=1)
        tf.total_input_tax_paid              = Decimal("0")
        tf.total_output_tax_collected        = Decimal("0")
        tf.total_sales_tax_paid              = Decimal("0")
        tf.total_wht_withheld_from_suppliers = Decimal("0")
        tf.total_wht_withheld_by_customers   = Decimal("0")
        tf.total_wht_paid                    = Decimal("0")
        tf.save()

        # 1. Input tax paid + WHT withheld from suppliers = sum of gst_total/wht_total
        #    on confirmed, non-data-entry purchase orders. Mirrors the exact same
        #    is_data_entry=False exclusion cash_flow's backfill uses for
        #    total_purchases_cash — data-entry orders (opening balance/opening
        #    stock) are carried-forward payables, not real taxed purchases.
        orders = PurchaseOrder.objects.filter(
            is_deleted=False,
            status="confirmed",
            is_data_entry=False,
        )
        for order in orders:
            tf.total_input_tax_paid              += order.gst_total or Decimal("0")
            tf.total_wht_withheld_from_suppliers += order.wht_total or Decimal("0")
        self.stdout.write(f"  total_input_tax_paid: {tf.total_input_tax_paid}")
        self.stdout.write(f"  total_wht_withheld_from_suppliers: {tf.total_wht_withheld_from_suppliers}")

        # 2. Output tax collected + WHT withheld by customers = sum of gst_total/
        #    wht_total on confirmed, non-data-entry, non-draft invoices. Mirrors
        #    the exact same real_invoices filter cash_flow's backfill uses for
        #    total_invoice_revenue.
        invoices = Invoice.objects.filter(
            is_deleted=False,
            is_data_entry=False,
        ).exclude(status="draft")
        for inv in invoices:
            tf.total_output_tax_collected      += inv.gst_total or Decimal("0")
            tf.total_wht_withheld_by_customers += inv.wht_total or Decimal("0")
        self.stdout.write(f"  total_output_tax_collected: {tf.total_output_tax_collected}")
        self.stdout.write(f"  total_wht_withheld_by_customers: {tf.total_wht_withheld_by_customers}")

        # 3. Sales tax actually paid to FBR = sum of non-deleted TaxPayment amounts
        payments = TaxPayment.objects.filter(is_deleted=False)
        for p in payments:
            tf.total_sales_tax_paid += p.amount
        self.stdout.write(f"  total_sales_tax_paid: {tf.total_sales_tax_paid}")

        # 4. WHT actually paid to FBR (supplier side only) = sum of non-deleted
        #    WHTPayment amounts
        wht_payments = WHTPayment.objects.filter(is_deleted=False)
        for wp in wht_payments:
            tf.total_wht_paid += wp.amount
        self.stdout.write(f"  total_wht_paid: {tf.total_wht_paid}")

        # Derived fields — same recompute-and-store discipline as the live sync path.
        tf.net_sales_tax_payable = tf.total_output_tax_collected - tf.total_input_tax_paid
        tf.sales_tax_outstanding = max(
            Decimal("0"), tf.net_sales_tax_payable - tf.total_sales_tax_paid
        )
        tf.wht_outstanding = max(
            Decimal("0"), tf.total_wht_withheld_from_suppliers - tf.total_wht_paid
        )

        tf.save()
        self.stdout.write(self.style.SUCCESS("\nTaxFlow backfill complete."))
        self.stdout.write(f"""
Final TaxFlow state:
  total_input_tax_paid              : {tf.total_input_tax_paid}
  total_output_tax_collected        : {tf.total_output_tax_collected}
  net_sales_tax_payable             : {tf.net_sales_tax_payable}
  total_sales_tax_paid              : {tf.total_sales_tax_paid}
  sales_tax_outstanding             : {tf.sales_tax_outstanding}
  total_wht_withheld_from_suppliers : {tf.total_wht_withheld_from_suppliers}
  total_wht_withheld_by_customers   : {tf.total_wht_withheld_by_customers}
  total_wht_paid                    : {tf.total_wht_paid}
  wht_outstanding                   : {tf.wht_outstanding}
""")
