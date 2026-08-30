from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Data-entry bootstrap models
#
# This app is a one-time bootstrap tool used by the superuser to seed opening
# data before go-live, then removed from production. Each opening balance is
# permanently locked after creation (no edit, no delete) — the OneToOneField
# guarantees exactly one per supplier/customer at the DB level.
# ---------------------------------------------------------------------------


class SupplierOpeningBalance(models.Model):
    supplier       = models.OneToOneField(
        "purchases.Supplier", on_delete=models.PROTECT, related_name="opening_balance",
    )
    amount         = models.DecimalField(max_digits=18, decimal_places=4)
    note           = models.TextField(blank=True, default="")
    purchase_order = models.OneToOneField(
        "purchases.PurchaseOrder", on_delete=models.PROTECT, related_name="opening_balance",
    )
    created_by     = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="supplier_opening_balances_created",
    )
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Supplier Opening Balance"
        verbose_name_plural = "Supplier Opening Balances"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"Opening balance {self.amount} — {self.supplier}"


class CustomerOpeningBalance(models.Model):
    customer   = models.OneToOneField(
        "billing.Customer", on_delete=models.PROTECT, related_name="opening_balance",
    )
    amount     = models.DecimalField(max_digits=18, decimal_places=4)
    note       = models.TextField(blank=True, default="")
    invoice    = models.OneToOneField(
        "billing.Invoice", on_delete=models.PROTECT, related_name="opening_balance",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="customer_opening_balances_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Customer Opening Balance"
        verbose_name_plural = "Customer Opening Balances"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"Opening balance {self.amount} — {self.customer}"


class OpeningCashEntry(models.Model):
    amount   = models.DecimalField(max_digits=18, decimal_places=4)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="opening_cash_entries",
    )
    added_at = models.DateTimeField(auto_now_add=True)
    note     = models.CharField(max_length=255, default="Opening cash added via data entry")

    class Meta:
        verbose_name        = "Opening Cash Entry"
        verbose_name_plural = "Opening Cash Entries"
        ordering            = ["-added_at"]

    def __str__(self):
        return f"Opening cash {self.amount}"
