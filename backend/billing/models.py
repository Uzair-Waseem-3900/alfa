from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Shared soft-delete infrastructure (mirrors purchases.models pattern)
# ---------------------------------------------------------------------------

class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset()


class AuditMixin(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="%(class)s_updated",
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="%(class)s_deleted",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class Customer(AuditMixin):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=100, unique=True)
    address = models.TextField()
    mobile = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


# ---------------------------------------------------------------------------
# Invoice (Bill)
# ---------------------------------------------------------------------------

class Invoice(AuditMixin):

    class Status(models.TextChoices):
        DRAFT     = "draft",     "Draft"
        CONFIRMED = "confirmed", "Confirmed"
        RETURNED  = "returned",  "Returned"       # fully returned
        PARTIAL   = "partial",   "Partially Returned"

    # Auto-generated bill number: BILL-2026-0001
    bill_number = models.CharField(max_length=30, unique=True, editable=False)
    customer    = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="invoices",
    )
    # Overrides AuditMixin.created_at to add an index — every invoice list
    # sorts by -created_at and filters by date range. Same pattern as
    # purchases.PurchaseOrder.
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)
    is_data_entry = models.BooleanField(
        default=False, db_index=True,
        help_text="True for bootstrap customer opening-balance invoices. Hidden from normal list views.",
    )
    status      = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True,
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="confirmed_invoices",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    payment_due_date = models.DateField(
        null=True, blank=True, db_index=True,
        help_text=(
            "Set by the user at invoice creation (defaults to +7 days if omitted). "
            "Carried through unchanged at confirmation. Editable at any time, "
            "including after confirmation, via the dedicated due-date endpoint."
        ),
    )

    class PaymentType(models.TextChoices):
        ADVANCE        = "advance",        "Advance Payment"
        AFTER_DELIVERY = "after_delivery", "Payment After Delivery"

    payment_type = models.CharField(
        max_length=20, choices=PaymentType.choices,
        default=PaymentType.AFTER_DELIVERY,
        help_text="Advance payment or payment after delivery.",
    )
    advance_amount = models.DecimalField(
        max_digits=18, decimal_places=4, default=0,
        help_text=(
            "Amount received in advance (only when payment_type=advance). "
            "Immediately added to cash_in_hand on draft creation. "
            "Capped at grand_total on confirmation."
        ),
    )

    class PaymentStatus(models.TextChoices):
        UNPAID  = "unpaid",  "Unpaid"
        PARTIAL = "partial", "Partial"
        PAID    = "paid",    "Paid"

    # Totals - computed and stored on confirmation
    subtotal      = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    gst_total     = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    wht_total     = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    grand_total   = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_cogs    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    gross_profit  = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    # Payment tracking - updated automatically on every Payment create/delete
    cash_received    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    credit_outstanding  = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_paid       = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    remaining_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    payment_status   = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        db_index=True,
    )

    class Meta:
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
        ordering = ["-created_at"]

    def __str__(self):
        return self.bill_number


# ---------------------------------------------------------------------------
# Invoice Line Item
# ---------------------------------------------------------------------------

class InvoiceItem(models.Model):
    """
    One row per product per invoice.
    Selling price is snapshotted from rate list at confirmation time.
    COGS (blended FIFO cost) is snapshotted at confirmation time.
    Both are immutable after confirmation.
    """

    invoice       = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    product       = models.ForeignKey(
        "purchases.Product", on_delete=models.PROTECT, related_name="invoice_items",
    )
    quantity      = models.PositiveIntegerField()

    # User-entered per line (default 0)
    discount = models.DecimalField(
        max_digits=10, decimal_places=4, default=0,
        help_text="Positive = price reduction. Negative = surcharge. effective_price = selling_price - discount",
    )
    gst = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="GST % e.g. 18.5")
    wht = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="WHT % e.g. 1.5")

    # Snapshotted at confirmation - never change after that
    selling_price      = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    effective_price    = models.DecimalField(max_digits=14, decimal_places=4, default=0,
                            help_text="selling_price - discount")
    cogs_per_unit      = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    line_gross         = models.DecimalField(max_digits=18, decimal_places=4, default=0,
                            help_text="quantity x effective_price")
    line_gst_amount    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    line_wht_amount    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    line_total         = models.DecimalField(max_digits=18, decimal_places=4, default=0,
                            help_text="line_gross + line_gst - line_wht (tax-inclusive)")
    line_cogs          = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    line_profit        = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    # Tracks how much of this line has been returned
    returned_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Invoice Item"
        verbose_name_plural = "Invoice Items"
        unique_together = [("invoice", "product")]   # one line per product per bill

    def __str__(self):
        return f"{self.invoice.bill_number} — {self.product.name}"

    @property
    def returnable_quantity(self):
        return self.quantity - self.returned_quantity

    @property
    def allocated_quantity(self):
        # Sums the in-memory prefetch cache when the caller prefetched
        # shelf_allocations (the normal list/detail path) — .aggregate()
        # would bypass that cache and re-query per item (N+1).
        return sum(a.quantity for a in self.shelf_allocations.all())


class InvoiceItemShelfAllocation(models.Model):
    """
    Draft plan for which shelf(s) this sale line is physically fulfilled
    from. Consumption, not put-away — only shelves currently holding stock
    of this product are valid (enforced by the selector listing candidates +
    the service-layer quantity check). Editable while the invoice is DRAFT;
    confirm_invoice blocks unless every item's allocations sum exactly to
    its quantity.
    """
    invoice_item = models.ForeignKey(InvoiceItem, on_delete=models.CASCADE, related_name="shelf_allocations")
    shelf        = models.ForeignKey("purchases.Shelf", on_delete=models.PROTECT, related_name="invoice_item_allocations")
    quantity     = models.PositiveIntegerField()
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Invoice Item Shelf Allocation"
        verbose_name_plural = "Invoice Item Shelf Allocations"
        unique_together     = [("invoice_item", "shelf")]

    def __str__(self):
        return f"{self.invoice_item} ← {self.shelf.name}: {self.quantity}"


# ---------------------------------------------------------------------------
# FIFO Ledger — tracks which purchase batches were consumed per invoice item
# ---------------------------------------------------------------------------

class FIFOLedger(models.Model):
    """
    Append-only record of which purchase batch supplied which invoice item.
    Created at confirmation time. Never edited or deleted.
    On return: a reverse entry is created (quantity negative) and
    remaining_quantity is restored on the purchase batch.
    """

    invoice_item = models.ForeignKey(
        InvoiceItem, on_delete=models.PROTECT, related_name="fifo_layers",
    )
    purchase     = models.ForeignKey(
        "purchases.PurchaseItem", on_delete=models.PROTECT, related_name="fifo_consumed",
    )
    quantity     = models.IntegerField(
        help_text="Positive = consumed. Negative = returned."
    )
    unit_cost    = models.DecimalField(max_digits=14, decimal_places=4)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "FIFO Ledger"
        verbose_name_plural = "FIFO Ledger Entries"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.invoice_item} ← Purchase#{self.purchase_id} × {self.quantity}"


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class Payment(AuditMixin):

    class Method(models.TextChoices):
        """
        Legacy label choices, kept for get_method_display()/backward
        compatibility. Since payment_methods.PaymentMethod (a real account,
        possibly user-created) replaced this as the actual source of truth,
        `method` can hold any account's name (lower-cased) or "multiple" for
        a split payment — values outside this list are still accepted at
        the ORM level (Django doesn't enforce `choices` on save()), they
        just fall back to showing the raw value via get_method_display().
        """
        CASH      = "cash",      "Cash"
        JAZZCASH  = "jazzcash",  "JazzCash"
        EASYPAISA = "easypaisa", "Easypaisa"
        BANK      = "bank",      "Bank Transfer"
        MULTIPLE  = "multiple",  "Multiple Methods"

    invoice          = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    reference_number = models.CharField(max_length=30, unique=True, editable=False,
                        #    default="", blank=True,
                           help_text="Auto-generated e.g. PAY-2026-0001")
    amount           = models.DecimalField(max_digits=18, decimal_places=4)
    method           = models.CharField(
        max_length=100, choices=Method.choices,
        help_text="Derived display label — see payment_methods.PaymentAllocation for the real split.",
    )
    payment_date     = models.DateField(db_index=True)
    note             = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ["-payment_date"]

    def __str__(self):
        return f"{self.invoice.bill_number} — {self.method} {self.amount}"


# ---------------------------------------------------------------------------
# Return
# ---------------------------------------------------------------------------

class Return(AuditMixin):
    """
    One return record per return event (whole bill or partial).
    Accepted only by admin/superuser.
    On acceptance: inventory incremented, FIFO ledger reversed, payment adjusted.
    """

    class Status(models.TextChoices):
        PENDING  = "pending",  "Pending"
        ACCEPTED = "accepted", "Accepted"

    invoice          = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="returns")
    reference_number = models.CharField(max_length=30, unique=True, editable=False,
                        #    default="", blank=True,
                           help_text="Auto-generated e.g. RTN-2026-0001")
    status           = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="accepted_returns",
    )
    accepted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Overrides AuditMixin.created_at to add an index — the returns list
    # sorts by -created_at and filters by date range.
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)
    note        = models.CharField(max_length=255, blank=True, default="")

    # Totals — computed on acceptance
    total_return_amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_return_cogs   = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        verbose_name = "Return"
        verbose_name_plural = "Returns"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Return for {self.invoice.bill_number}"


# ---------------------------------------------------------------------------
# Return Item
# ---------------------------------------------------------------------------

class ReturnItem(models.Model):
    """
    One row per product being returned in a Return event.
    """

    return_record = models.ForeignKey(Return, on_delete=models.CASCADE, related_name="items")
    invoice_item  = models.ForeignKey(InvoiceItem, on_delete=models.PROTECT, related_name="return_items")
    quantity      = models.PositiveIntegerField()

    # Snapshotted from original invoice item at acceptance
    selling_price = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    cogs_per_unit = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    line_total    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    line_cogs     = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        verbose_name = "Return Item"
        verbose_name_plural = "Return Items"
        unique_together = [("return_record", "invoice_item")]

    def __str__(self):
        return f"{self.return_record} — {self.invoice_item.product.name} × {self.quantity}"

    @property
    def allocated_quantity(self):
        # Sums the in-memory prefetch cache when the caller prefetched
        # shelf_allocations (the normal list/detail path) — .aggregate()
        # would bypass that cache and re-query per item (N+1).
        return sum(a.quantity for a in self.shelf_allocations.all())


class InvoiceReturnItemShelfAllocation(models.Model):
    """
    Draft plan for which shelf(s) a customer-returned quantity is physically
    put away onto. Put-away, not consumption — any shelf is a valid choice.
    Editable while the return is PENDING; accept_return blocks unless every
    item's allocations sum exactly to its quantity.
    """
    return_item = models.ForeignKey(ReturnItem, on_delete=models.CASCADE, related_name="shelf_allocations")
    shelf       = models.ForeignKey("purchases.Shelf", on_delete=models.PROTECT, related_name="invoice_return_item_allocations")
    quantity    = models.PositiveIntegerField()
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Invoice Return Item Shelf Allocation"
        verbose_name_plural = "Invoice Return Item Shelf Allocations"
        unique_together     = [("return_item", "shelf")]

    def __str__(self):
        return f"{self.return_item} → {self.shelf.name}: {self.quantity}"


# ---------------------------------------------------------------------------
# Saved Invoice PDF
# ---------------------------------------------------------------------------

class SavedInvoicePDF(models.Model):
    """
    Tracks every PDF file saved by a user for an invoice.
    Files stored at: media/invoices/<year>/<bill_number>_<timestamp>.pdf
    Soft-deleted on user request (file also removed from disk via service).
    """

    invoice    = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="saved_pdfs")
    file_name  = models.CharField(max_length=255, help_text="User-supplied or default name.")
    file_path  = models.CharField(max_length=500)
    is_draft   = models.BooleanField(default=False, help_text="True if saved with DRAFT watermark.")
    saved_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="saved_pdfs",
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="deleted_pdfs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects     = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        verbose_name = "Saved Invoice PDF"
        verbose_name_plural = "Saved Invoice PDFs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.invoice.bill_number} - {self.file_name}"