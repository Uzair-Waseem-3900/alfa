from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# RecurringExpenseCategory
# ---------------------------------------------------------------------------

class RecurringExpenseCategory(models.Model):
    """
    A separate category concept from cash_flow.ExpenseCategory — scoped only
    to recurring expenses (Rent, Salaries, Utilities, ...). Soft-deletable:
    "deleting" a category only hides it from active use (create/assign
    dropdowns) — every RecurringExpenseAssignment already snapshotted its own
    category_name at assignment time, so history is never affected either way.
    """

    name        = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="recurring_expense_categories_created",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recurring_expense_categories_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Recurring Expense Category"
        verbose_name_plural  = "Recurring Expense Categories"
        ordering             = ["name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# RecurringExpense  (the template — a monthly obligation)
# ---------------------------------------------------------------------------

class RecurringExpense(models.Model):
    """
    A template for something that recurs every month — a salary, rent, a
    subscription. Never itself a cash movement — only its
    RecurringExpenseAssignment postings are. amount/category are editable any
    time; edits only affect assignments created AFTER the change (already-
    assigned months keep their own snapshotted values forever).

    is_active controls whether this template can still be assigned for new
    months — turning it off (e.g. an employee resigns) just stops it showing
    up as due; it can be turned back on later. No proration is ever applied
    for a start/end mid-month — an assigned month always posts the full
    amount.
    """

    name        = models.CharField(max_length=255)
    category    = models.ForeignKey(RecurringExpenseCategory, on_delete=models.PROTECT, related_name="recurring_expenses")
    amount      = models.DecimalField(max_digits=18, decimal_places=4)
    start_date  = models.DateField(help_text="First month this obligation is eligible to be assigned.")
    is_active   = models.BooleanField(default=True, db_index=True)
    note        = models.TextField(blank=True, default="")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="recurring_expenses_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="recurring_expenses_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recurring_expenses_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Recurring Expense"
        verbose_name_plural  = "Recurring Expenses"
        ordering             = ["name"]

    def __str__(self):
        return f"{self.name} ({self.amount}/mo)"


# ---------------------------------------------------------------------------
# RecurringExpenseAssignment  (one month's due amount for one template)
# ---------------------------------------------------------------------------

class RecurringExpenseAssignment(models.Model):
    """
    "This template owes this much for this month." Created explicitly by the
    user (single or bulk "Post"/"Assign" action) — never auto-created, never
    updated once created. Only amount_paid/payment_status move, and only as
    a side effect of RecurringExpenseAssignmentPayment rows.

    Soft-deletable, but ONLY while still fully unpaid (amount_paid == 0) —
    lets a mistaken assignment (wrong template, wrong period) be undone
    cleanly. Once any payment has been recorded against it, it can no longer
    be unassigned; delete the payment(s) first via
    delete_recurring_expense_payment. See services.delete_recurring_expense_assignment.

    name_snapshot / category_name_snapshot freeze the template's name and
    category exactly as they were at assignment time — a later template
    rename/re-category, or category rename/delete, never rewrites history.

    The unique constraint below only applies to non-deleted rows — unassigning
    a mistaken entry frees up that template/period combination for a fresh,
    correct assignment.
    """

    class PaymentStatus(models.TextChoices):
        UNPAID  = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partial"
        PAID    = "paid", "Paid"

    recurring_expense       = models.ForeignKey(RecurringExpense, on_delete=models.PROTECT, related_name="assignments")
    period                  = models.CharField(max_length=7, db_index=True, help_text="YYYY-MM this assignment is for.")
    name_snapshot           = models.CharField(max_length=255)
    category                = models.ForeignKey(RecurringExpenseCategory, on_delete=models.PROTECT, related_name="assignments")
    category_name_snapshot  = models.CharField(max_length=255)
    amount                  = models.DecimalField(max_digits=18, decimal_places=4, help_text="Assigned amount, frozen from the template at assignment time.")
    amount_paid             = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    payment_status          = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID, db_index=True)
    note                    = models.TextField(blank=True, default="")

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="recurring_expense_assignments_created",
    )
    # Indexed — this is the field reports.selectors' Recurring Expenses
    # report filters/orders by (and Meta.ordering's own sort key), mirroring
    # PurchaseOrder/PurchaseReturn/LostInventoryRecord's same override.
    assigned_at = models.DateTimeField(auto_now_add=True, db_index=True)

    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recurring_expense_assignments_deleted",
    )
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Recurring Expense Assignment"
        verbose_name_plural  = "Recurring Expense Assignments"
        ordering             = ["-period", "-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["recurring_expense", "period"],
                condition=models.Q(is_deleted=False),
                name="unique_recurring_expense_assignment_per_period",
            ),
        ]
        indexes = [
            models.Index(fields=["period", "category"], name="idx_rea_period_category"),
        ]

    def __str__(self):
        return f"{self.name_snapshot} — {self.period}: {self.amount} ({self.payment_status})"


# ---------------------------------------------------------------------------
# RecurringExpenseAssignmentPayment  (mirrors purchases.SupplierPayment)
# ---------------------------------------------------------------------------

class RecurringExpenseAssignmentPayment(models.Model):
    """
    One payment made against a RecurringExpenseAssignment. This is the ONLY
    moment cash actually leaves the business for a recurring expense —
    assigning a month never touches cash_in_hand, only a payment does.
    Soft-deletable (a genuine mistake can be reversed) — deletion must
    reverse all four synced places at once: the assignment's own
    amount_paid/payment_status, CashFlow.cash_in_hand +
    total_recurring_expenses_paid, RecurringExpenseFlow, and that period's
    RecurringExpenseMonthlyStats row. See services.delete_recurring_expense_payment.
    """

    assignment    = models.ForeignKey(RecurringExpenseAssignment, on_delete=models.PROTECT, related_name="payments")
    amount        = models.DecimalField(max_digits=18, decimal_places=4)
    payment_date  = models.DateField(db_index=True)
    note          = models.TextField(blank=True, default="")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="recurring_expense_payments_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="recurring_expense_payments_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recurring_expense_payments_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Recurring Expense Payment"
        verbose_name_plural  = "Recurring Expense Payments"
        ordering             = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"Payment {self.amount} on {self.assignment} ({self.payment_date})"


# ---------------------------------------------------------------------------
# RecurringExpenseFlow  (singleton — mirrors cash_flow.CashFlow)
# ---------------------------------------------------------------------------

class RecurringExpenseFlow(models.Model):
    """
    Single live record — O(1) dashboard reads for this app. Never created
    manually — managed exclusively via recurring_expenses.services.
    """

    total_assigned_amount = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                 help_text="Sum of every RecurringExpenseAssignment.amount ever created, all-time. Only ever increases.")
    total_paid_amount     = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                 help_text="Sum of every non-deleted payment ever made, all-time.")
    total_pending_amount  = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                 help_text="total_assigned_amount - total_paid_amount, floored at 0. Stored, recalculated on every sync.")
    total_assignments_count = models.PositiveIntegerField(default=0)

    total_active_templates          = models.PositiveIntegerField(default=0,
                                            help_text="Count of active, non-deleted RecurringExpense templates.")
    total_active_monthly_obligation = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                            help_text="Sum of amount across active templates — what would be owed this month if everything were assigned.")

    last_updated_at = models.DateTimeField(auto_now=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="recurring_expense_flow_updates",
    )

    class Meta:
        verbose_name        = "Recurring Expense Flow"
        verbose_name_plural  = "Recurring Expense Flow"

    def __str__(self):
        return f"RecurringExpenseFlow — pending: {self.total_pending_amount}"

    @classmethod
    def get_instance(cls):
        """Always returns the single RecurringExpenseFlow record, creating it if needed."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance


# ---------------------------------------------------------------------------
# RecurringExpenseMonthlyStats  (one synced row per period — the monthly breakdown)
# ---------------------------------------------------------------------------

class RecurringExpenseMonthlyStats(models.Model):
    """
    One row per calendar month, stored and incrementally updated — never
    computed live. A payment always updates the row for the ASSIGNMENT's own
    period, regardless of which month the payment itself was recorded in
    (e.g. a July rent assignment paid in August still updates July's row) —
    this is what lets "is July fully settled?" stay answerable at a glance,
    independent of payment timing. Each period's row is fully independent —
    it never rolls over into or merges with the next month.
    """

    period          = models.CharField(max_length=7, unique=True, db_index=True, help_text="YYYY-MM")
    total_assigned  = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    total_paid      = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    total_pending   = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                           help_text="total_assigned - total_paid, floored at 0. Stored, recalculated on every sync.")
    is_fully_paid   = models.BooleanField(default=False, db_index=True,
                           help_text="True exactly when total_pending reaches 0 and total_assigned > 0.")

    last_updated_at = models.DateTimeField(auto_now=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Recurring Expense Monthly Stats"
        verbose_name_plural  = "Recurring Expense Monthly Stats"
        ordering             = ["-period"]

    def __str__(self):
        return f"{self.period} — assigned {self.total_assigned}, paid {self.total_paid}, pending {self.total_pending}"

    @classmethod
    def get_for_period(cls, period: str):
        """Always returns the row for this period, creating it if needed."""
        instance, _ = cls.objects.get_or_create(period=period)
        return instance
