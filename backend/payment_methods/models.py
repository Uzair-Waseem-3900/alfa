from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Shared soft-delete infrastructure (mirrors billing.models / purchases.models pattern)
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

    objects     = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# PaymentMethod  (a real "account" — Cash, JazzCash, Easypaisa, Bank, ...)
# ---------------------------------------------------------------------------

class PaymentMethod(AuditMixin):
    """
    Replaces the old predefined cash/jazzcash/easypaisa/bank labels. Each
    row is a real account with its own running balance. `balance` is O(1)
    — a stored, service-updated total, never recomputed at read time, same
    pattern as cash_management.Investor.net_stake / CashFlow.cash_in_hand.

    The `Cash` row is seeded once (via the seed_and_backfill_payment_methods
    management command) with is_protected=True: it can never be renamed or
    deleted at the service layer, since every historical transaction in
    this system was normalized onto it before this model existed.
    """

    name           = models.CharField(max_length=100, unique=True)
    account_number = models.CharField(max_length=100, blank=True, default="")
    balance        = models.DecimalField(
        max_digits=20, decimal_places=4, default=0,
        help_text="Running balance for this method. Only ever written by "
                   "payment_methods.services — never recomputed at read time.",
    )
    is_protected   = models.BooleanField(
        default=False,
        help_text="True only on the seeded Cash row. Blocks rename and "
                   "delete at the service layer.",
    )

    class Meta:
        verbose_name        = "Payment Method"
        verbose_name_plural  = "Payment Methods"
        ordering             = ["name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# PaymentAllocation  (one row per method used in a transaction)
# ---------------------------------------------------------------------------

class PaymentAllocation(models.Model):
    """
    One row per method used in a single inflow/outflow. A split payment
    (e.g. an invoice payment of 1000 = 400 Cash + 600 JazzCash) produces
    two rows sharing the same (source_model, source_id) — deliberately NOT
    unique-constrained on that pair, unlike cash_flow.CashMovement, since a
    split source legitimately needs more than one row.

    Written exclusively by the Phase 2 allocation engine
    (payment_methods.services.record_allocations / reverse_allocations /
    refresh_allocations) — never created directly elsewhere.
    """

    class Direction(models.TextChoices):
        INFLOW  = "inflow", "Inflow"
        OUTFLOW = "outflow", "Outflow"

    payment_method = models.ForeignKey(
        PaymentMethod, on_delete=models.PROTECT, related_name="allocations",
    )
    source_model = models.CharField(max_length=60, help_text="app_label.model_name of the row that caused this allocation.")
    source_id    = models.BigIntegerField()
    direction    = models.CharField(max_length=10, choices=Direction.choices)
    amount       = models.DecimalField(max_digits=20, decimal_places=4)
    date         = models.DateField()

    is_deleted = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()

    class Meta:
        verbose_name        = "Payment Allocation"
        verbose_name_plural  = "Payment Allocations"
        ordering             = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["source_model", "source_id"], name="idx_alloc_source"),
            models.Index(fields=["payment_method", "is_deleted"], name="idx_alloc_method_active"),
        ]

    def __str__(self):
        return f"{self.payment_method} — {self.direction} {self.amount}"


# ---------------------------------------------------------------------------
# AccountTransfer  (move a balance from one method to another)
# ---------------------------------------------------------------------------

class AccountTransfer(AuditMixin):
    """
    Moves balance directly between two PaymentMethod rows — e.g. "move 100
    from Cash to JazzCash". Never touches cash_in_hand: no real cash enters
    or leaves the business, it just changes which account holds it.

    Model only in Phase 1 — its create/list API and the balance-moving
    service are built in Phase 6.
    """

    from_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name="transfers_out")
    to_method   = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, related_name="transfers_in")
    amount      = models.DecimalField(max_digits=20, decimal_places=4)
    date        = models.DateField()
    note        = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name        = "Account Transfer"
        verbose_name_plural  = "Account Transfers"
        ordering             = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.from_method} → {self.to_method} — {self.amount}"
