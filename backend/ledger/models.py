from django.conf import settings
from django.db import models


class SupplierLedger(models.Model):
    """
    One per supplier. Auto-created when supplier is created.
    Stores supplier name/code as snapshot fields so historical
    data is preserved even if supplier is soft-deleted or renamed.
    """
    supplier      = models.OneToOneField(
        "purchases.Supplier",
        on_delete=models.PROTECT,
        related_name="ledger",
    )
    supplier_name = models.CharField(max_length=255)   # snapshot
    supplier_code = models.CharField(max_length=100)   # snapshot
    created_at    = models.DateTimeField(auto_now_add=True)

    # Soft delete — only allowed once the linked supplier is itself
    # soft-deleted (enforced in services.delete_ledger).
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="deleted_supplier_ledgers",
    )

    class Meta:
        verbose_name        = "Supplier Ledger"
        verbose_name_plural = "Supplier Ledgers"
        ordering            = ["supplier_name"]

    def __str__(self):
        return f"Ledger — {self.supplier_name} ({self.supplier_code})"


class SupplierLedgerEntry(models.Model):
    """
    One row per transaction. Stores only debit/credit amounts.
    Running balance is computed at query time using monthly snapshots.

    entry_type:
        purchase  → PO confirmed            → credit increases (we owe more)
        payment   → supplier payment made   → debit increases (we paid)
        return    → purchase return accepted → debit increases (debt reduced)
        advance   → advance on draft PO     → debit increases (paid upfront)
    """

    class EntryType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        PAYMENT  = "payment",  "Payment"
        RETURN   = "return",   "Return"
        ADVANCE  = "advance",  "Advance Payment"
        OPENING_BALANCE = "opening_balance", "Opening Balance"

    ledger          = models.ForeignKey(SupplierLedger, on_delete=models.PROTECT, related_name="entries")
    entry_type      = models.CharField(max_length=20, choices=EntryType.choices, db_index=True)
    date            = models.DateField(db_index=True)
    details         = models.CharField(max_length=500)
    reference       = models.CharField(max_length=50, db_index=True)
    debit           = models.DecimalField(max_digits=18, decimal_places=4, default=0,
                          help_text="Money we paid to supplier (payment/return/advance).")
    credit          = models.DecimalField(max_digits=18, decimal_places=4, default=0,
                          help_text="Amount we owe supplier (purchase confirmed).")
    created_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="ledger_entries_created",
    )
    created_at      = models.DateTimeField(auto_now_add=True)

    # Links to source records (nullable — for easy reverse lookup)
    purchase_order  = models.ForeignKey(
        "purchases.PurchaseOrder", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ledger_entries",
    )
    supplier_payment = models.ForeignKey(
        "purchases.SupplierPayment", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ledger_entries",
    )
    purchase_return = models.ForeignKey(
        "purchases.PurchaseReturn", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ledger_entries",
    )

    class Meta:
        verbose_name        = "Supplier Ledger Entry"
        verbose_name_plural = "Supplier Ledger Entries"
        ordering            = ["date", "created_at"]
        indexes             = [
            models.Index(fields=["ledger", "date"], name="idx_ledger_entry_date"),
        ]

    def __str__(self):
        return f"{self.ledger.supplier_code} | {self.date} | {self.entry_type} | ref:{self.reference}"


class SupplierLedgerSnapshot(models.Model):
    """
    Closing balance at end of each month for a supplier.
    Used by hybrid balance calculation to avoid iterating all entries.

    closing_balance = payable_outstanding at end of year_month.
    Recalculated when entries in that month or prior months change.
    """
    ledger          = models.ForeignKey(SupplierLedger, on_delete=models.PROTECT, related_name="snapshots")
    year_month      = models.CharField(max_length=7, db_index=True,
                          help_text="Format: YYYY-MM e.g. 2026-06")
    closing_balance = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Supplier Ledger Snapshot"
        verbose_name_plural = "Supplier Ledger Snapshots"
        unique_together     = [("ledger", "year_month")]
        ordering            = ["year_month"]

    def __str__(self):
        return f"{self.ledger.supplier_code} | {self.year_month} | balance:{self.closing_balance}"


class SavedLedgerPDF(models.Model):
    """
    Tracks every saved PDF for a supplier ledger.
    """
    ledger     = models.ForeignKey(SupplierLedger, on_delete=models.PROTECT, related_name="saved_pdfs")
    file_name  = models.CharField(max_length=255)
    file_path  = models.CharField(max_length=500)
    date_from  = models.DateField(null=True, blank=True)
    date_to    = models.DateField(null=True, blank=True)
    saved_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="saved_ledger_pdfs",
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="deleted_ledger_pdfs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name        = "Saved Ledger PDF"
        verbose_name_plural = "Saved Ledger PDFs"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"{self.ledger.supplier_code} — {self.file_name}"


# ---------------------------------------------------------------------------
# Customer ledger — mirror of the supplier ledger above, direction flipped.
#
# Sale (invoice confirmed)  → Debit  (customer owes us more)
# Payment / Advance / Return → Credit (customer owes us less)
# ---------------------------------------------------------------------------

class CustomerLedger(models.Model):
    """
    One per customer. Auto-created when customer is created.
    Stores customer name/code as snapshot fields so historical data is
    preserved even if the customer is soft-deleted or renamed.
    """
    customer      = models.OneToOneField(
        "billing.Customer",
        on_delete=models.PROTECT,
        related_name="ledger",
    )
    customer_name = models.CharField(max_length=255)   # snapshot
    customer_code = models.CharField(max_length=100)   # snapshot
    created_at    = models.DateTimeField(auto_now_add=True)

    # Soft delete — only allowed once the linked customer is itself
    # soft-deleted (enforced in services.delete_customer_ledger).
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="deleted_customer_ledgers",
    )

    class Meta:
        verbose_name        = "Customer Ledger"
        verbose_name_plural = "Customer Ledgers"
        ordering            = ["customer_name"]

    def __str__(self):
        return f"Ledger — {self.customer_name} ({self.customer_code})"


class CustomerLedgerEntry(models.Model):
    """
    One row per transaction. Stores only debit/credit amounts.
    Running balance is computed at query time using monthly snapshots.

    entry_type:
        sale             → invoice confirmed         → debit increases (they owe more)
        payment          → payment received          → credit increases (they owe less)
        return           → return accepted           → credit increases (debt reduced)
        advance          → advance on draft invoice   → credit increases (paid upfront)
        opening_balance  → data-entry bootstrap       → debit increases (they owed from before go-live)
    """

    class EntryType(models.TextChoices):
        SALE     = "sale",     "Sale"
        PAYMENT  = "payment",  "Payment"
        RETURN   = "return",   "Return"
        ADVANCE  = "advance",  "Advance Payment"
        OPENING_BALANCE = "opening_balance", "Opening Balance"

    ledger          = models.ForeignKey(CustomerLedger, on_delete=models.PROTECT, related_name="entries")
    entry_type      = models.CharField(max_length=20, choices=EntryType.choices, db_index=True)
    date            = models.DateField(db_index=True)
    details         = models.CharField(max_length=500)
    reference       = models.CharField(max_length=50, db_index=True)
    debit           = models.DecimalField(max_digits=18, decimal_places=4, default=0,
                          help_text="Amount the customer owes us more (sale/opening balance).")
    credit          = models.DecimalField(max_digits=18, decimal_places=4, default=0,
                          help_text="Amount the customer owes us less (payment/advance/return).")
    created_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="customer_ledger_entries_created",
    )
    created_at      = models.DateTimeField(auto_now_add=True)

    # Links to source records (nullable — for easy reverse lookup)
    invoice = models.ForeignKey(
        "billing.Invoice", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ledger_entries",
    )
    payment = models.ForeignKey(
        "billing.Payment", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ledger_entries",
    )
    customer_return = models.ForeignKey(
        "billing.Return", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="ledger_entries",
    )

    class Meta:
        verbose_name        = "Customer Ledger Entry"
        verbose_name_plural = "Customer Ledger Entries"
        ordering            = ["date", "created_at"]
        indexes             = [
            models.Index(fields=["ledger", "date"], name="idx_cust_ledger_entry_date"),
        ]

    def __str__(self):
        return f"{self.ledger.customer_code} | {self.date} | {self.entry_type} | ref:{self.reference}"


class CustomerLedgerSnapshot(models.Model):
    """
    Closing balance at end of each month for a customer.
    Used by hybrid balance calculation to avoid iterating all entries.

    closing_balance = receivable_outstanding at end of year_month.
    Recalculated when entries in that month or prior months change.
    """
    ledger          = models.ForeignKey(CustomerLedger, on_delete=models.PROTECT, related_name="snapshots")
    year_month      = models.CharField(max_length=7, db_index=True,
                          help_text="Format: YYYY-MM e.g. 2026-06")
    closing_balance = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Customer Ledger Snapshot"
        verbose_name_plural = "Customer Ledger Snapshots"
        unique_together     = [("ledger", "year_month")]
        ordering            = ["year_month"]

    def __str__(self):
        return f"{self.ledger.customer_code} | {self.year_month} | balance:{self.closing_balance}"


class SavedCustomerLedgerPDF(models.Model):
    """
    Tracks every saved PDF for a customer ledger.
    """
    ledger     = models.ForeignKey(CustomerLedger, on_delete=models.PROTECT, related_name="saved_pdfs")
    file_name  = models.CharField(max_length=255)
    file_path  = models.CharField(max_length=500)
    date_from  = models.DateField(null=True, blank=True)
    date_to    = models.DateField(null=True, blank=True)
    saved_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="saved_customer_ledger_pdfs",
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="deleted_customer_ledger_pdfs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    class Meta:
        verbose_name        = "Saved Customer Ledger PDF"
        verbose_name_plural = "Saved Customer Ledger PDFs"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"{self.ledger.customer_code} — {self.file_name}"