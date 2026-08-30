from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# TaxFlow  (singleton — one live record, auto-synced, mirrors cash_flow.CashFlow)
# ---------------------------------------------------------------------------

class TaxFlow(models.Model):
    """
    Single live record representing the store's current sales-tax (GST) and
    withholding-tax (WHT) position. Never created manually — managed
    exclusively via taxes.services. Updated atomically whenever a purchase
    order or invoice is confirmed, or a tax payment is recorded.

    total_input_tax_paid / total_output_tax_collected / net_sales_tax_payable
    / total_sales_tax_paid / sales_tax_outstanding:
        + purchase order confirmed  -> total_input_tax_paid increases
        + invoice confirmed         -> total_output_tax_collected increases
        + tax payment recorded      -> total_sales_tax_paid increases
        net_sales_tax_payable and sales_tax_outstanding are recalculated and
        SAVED (not just computed on read) every time any of the above happens.
        Known v1 limitation: purchase/customer returns do NOT reduce these
        totals (same "only ever increases" convention as every other running
        total in this project) — flagged, not silently decided.

    total_wht_withheld_from_suppliers / total_wht_withheld_by_customers:
        Read-only informational totals. No payment tracking in v1 — see
        taxes/README.md for exactly why these two behave differently.
    """

    # ---- Sales Tax (GST) — this is the tax you actually reconcile/pay ----
    total_input_tax_paid = models.DecimalField(
        max_digits=20, decimal_places=4, default=0,
        help_text="GST paid to suppliers, all-time (gross, only ever increases). "
                   "This is money already spent — legally deductible from what you owe FBR.",
    )
    total_output_tax_collected = models.DecimalField(
        max_digits=20, decimal_places=4, default=0,
        help_text="GST charged to customers, all-time (gross, only ever increases). "
                   "This is money you're holding on FBR's behalf, not yours to keep.",
    )
    net_sales_tax_payable = models.DecimalField(
        max_digits=20, decimal_places=4, default=0,
        help_text="output_tax_collected - input_tax_paid. What you'd owe FBR if "
                   "registered and filing today. Stored field, recalculated on every sync.",
    )
    total_sales_tax_paid = models.DecimalField(
        max_digits=20, decimal_places=4, default=0,
        help_text="Actual GST payments made (via TaxPayment records), all-time "
                   "(gross, only ever increases).",
    )
    sales_tax_outstanding = models.DecimalField(
        max_digits=20, decimal_places=4, default=0,
        help_text="net_sales_tax_payable - total_sales_tax_paid, floored at 0. "
                   "What's left to pay right now.",
    )

    # ---- Withholding Tax (WHT) — supplier side is payment-tracked, customer side stays informational ----
    total_wht_withheld_from_suppliers = models.DecimalField(
        max_digits=20, decimal_places=4, default=0,
        help_text="Tax you deducted from supplier payments, all-time. Real cash you "
                   "owe FBR — a liability, now payment-tracked via WHTPayment.",
    )
    total_wht_withheld_by_customers = models.DecimalField(
        max_digits=20, decimal_places=4, default=0,
        help_text="Tax customers deducted from what they paid you, all-time. You never "
                   "touch this money — it's a credit for your own annual return. Never "
                   "netted against total_wht_withheld_from_suppliers — different taxpayer's "
                   "obligation, informational only.",
    )
    total_wht_paid = models.DecimalField(
        max_digits=20, decimal_places=4, default=0,
        help_text="Actual WHT deposits made to FBR (via WHTPayment records) against tax "
                   "withheld from suppliers, all-time (gross, only ever increases).",
    )
    wht_outstanding = models.DecimalField(
        max_digits=20, decimal_places=4, default=0,
        help_text="total_wht_withheld_from_suppliers - total_wht_paid, floored at 0. "
                   "What's still owed to FBR from tax already withheld from suppliers. "
                   "Never netted against total_wht_withheld_by_customers — see docstring above.",
    )

    # ---- Last sync metadata ----
    last_updated_at = models.DateTimeField(auto_now=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="taxflow_updates",
    )

    class Meta:
        verbose_name        = "Tax Flow"
        verbose_name_plural  = "Tax Flow"

    def __str__(self):
        return f"TaxFlow — sales_tax_outstanding: {self.sales_tax_outstanding}"

    @classmethod
    def get_instance(cls):
        """Always returns the single TaxFlow record, creating it if needed."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance


# ---------------------------------------------------------------------------
# TaxPayment  (ledger — mirrors cash_flow.Expense)
# ---------------------------------------------------------------------------

class TaxPayment(models.Model):
    """
    A real GST payment made to FBR. Confirmed immediately on creation — no
    draft state. Amount auto-deducted from CashFlow.cash_in_hand on create,
    restored on delete. Full audit trail via created_by/updated_by/deleted_by.
    """

    amount       = models.DecimalField(max_digits=18, decimal_places=4)
    payment_date = models.DateField(db_index=True)
    note         = models.TextField(blank=True, default="")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="tax_payments_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="tax_payments_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="tax_payments_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Tax Payment"
        verbose_name_plural  = "Tax Payments"
        ordering             = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"Tax Payment — {self.amount} on {self.payment_date}"


# ---------------------------------------------------------------------------
# WHTPayment  (ledger — mirrors TaxPayment, tracks deposits against WHT withheld from suppliers)
# ---------------------------------------------------------------------------

class WHTPayment(models.Model):
    """
    A real WHT deposit made to FBR, against tax previously withheld from
    supplier payments. Confirmed immediately on creation — no draft state.
    Amount auto-deducted from CashFlow.cash_in_hand on create, restored on
    delete. Full audit trail via created_by/updated_by/deleted_by.

    Only tracks the supplier side (total_wht_withheld_from_suppliers) — WHT
    withheld by customers is never paid by this business, so it has no
    payment ledger; see TaxFlow docstring.
    """

    amount       = models.DecimalField(max_digits=18, decimal_places=4)
    payment_date = models.DateField(db_index=True)
    note         = models.TextField(blank=True, default="")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="wht_payments_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="wht_payments_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="wht_payments_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "WHT Payment"
        verbose_name_plural  = "WHT Payments"
        ordering             = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"WHT Payment — {self.amount} on {self.payment_date}"
