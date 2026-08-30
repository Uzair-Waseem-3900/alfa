from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# Expense Category
# ---------------------------------------------------------------------------

class ExpenseCategory(models.Model):
    name        = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="expense_categories_created",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Expense Category"
        verbose_name_plural = "Expense Categories"
        ordering            = ["name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Expense
# ---------------------------------------------------------------------------

class Expense(models.Model):
    """
    Confirmed immediately on creation — no draft state.
    Amount auto-deducted from CashFlow.cash_in_hand on create.
    On edit: cash_in_hand adjusted by difference (old - new).
    On delete: cash_in_hand restored by current amount.
    Full audit trail via created_by/updated_by/deleted_by.
    """

    name         = models.CharField(max_length=255)
    category     = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="expenses",
    )
    description  = models.TextField(blank=True, default="")
    amount       = models.DecimalField(max_digits=18, decimal_places=4)
    expense_date = models.DateField(db_index=True)

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="expenses_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="expenses_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="expenses_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Expense"
        verbose_name_plural = "Expenses"
        ordering            = ["-expense_date", "-created_at"]

    def __str__(self):
        return f"{self.name} — {self.amount}"


# ---------------------------------------------------------------------------
# CashMovement  (event table — one row per cash_in_hand movement)
# ---------------------------------------------------------------------------

class CashMovement(models.Model):
    """
    One row per event that moved cash_in_hand — written at the same moment
    (inside the same transaction) as the CashFlow adjustment, by
    services.record_cash_movement()/refresh_cash_movement()/
    reverse_cash_movement() ONLY. Powers the cash-in-hand breakdown drawer
    with a single indexed query instead of materializing every row from all
    14 source tables in Python.

    description/reference/method are snapshots of exactly what the drawer
    displayed at the moment the event happened (the same f-strings the old
    Python merge built). source_model + source_id tie each event back to the
    row that caused it, so deleting/reversing the source soft-deletes the
    event, and `backfill_cash_movements` can rebuild the whole table from
    the sources at any time (it is also the repair tool).

    NOT the source of truth for balances — CashFlow's stored totals remain
    that; get_cash_flow_totals_up_to() stays derived from the source tables
    as an independent cross-check.
    """

    class Direction(models.TextChoices):
        INFLOW  = "inflow", "Inflow"
        OUTFLOW = "outflow", "Outflow"

    direction     = models.CharField(max_length=10, choices=Direction.choices)
    movement_type = models.CharField(max_length=40)
    date          = models.DateField(help_text="Business date shown in the drawer (payment/expense/... date).")
    occurred_at   = models.DateTimeField(help_text="Source row's created_at — the drawer's sort key.")
    description   = models.CharField(max_length=500)
    reference     = models.CharField(max_length=100)
    method        = models.CharField(max_length=30, null=True, blank=True)
    amount        = models.DecimalField(max_digits=20, decimal_places=4)

    source_model  = models.CharField(max_length=60, help_text="app_label.model_name of the row that caused this event.")
    source_id     = models.BigIntegerField()

    is_deleted    = models.BooleanField(default=False)
    created_at    = models.DateTimeField(auto_now_add=True)

    objects       = models.Manager()

    class Meta:
        verbose_name        = "Cash Movement"
        verbose_name_plural = "Cash Movements"
        ordering            = ["-occurred_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_model", "source_id"], name="uniq_cashmove_source",
            ),
        ]
        indexes = [
            # Drawer's default read: active rows, newest first.
            models.Index(fields=["is_deleted", "-occurred_at"], name="idx_cashmove_active_occurred"),
            # Same read with the inflow/outflow filter applied.
            models.Index(fields=["is_deleted", "direction", "-occurred_at"], name="idx_cashmove_dir_occurred"),
            # Business-date range filters.
            models.Index(fields=["date"], name="idx_cashmove_date"),
        ]

    def __str__(self):
        return f"{self.direction} {self.amount} — {self.description}"


# ---------------------------------------------------------------------------
# CashFlow  (singleton — one live record, auto-synced)
# ---------------------------------------------------------------------------

class CashFlow(models.Model):
    """
    Single live record representing the current state of business finances.
    Never created manually — managed exclusively via CashFlowService.
    Updated atomically on every transaction event.

    cash_in_hand:
        + invoice payments received (all methods)
        - expenses created
        - advance supplier payments (on draft PO creation)
        Adjusts on edits and deletes.

    customer_outstanding:
        + invoice confirmed (full grand_total)
        - invoice payment received
        - invoice return credit note

    supplier_payable_outstanding:
        + purchase order confirmed (full net_payable)
        - supplier payment made
        - purchase return credit note
        - advance amount (already paid on draft creation)

    total_lost_inventory_worth:
        + lost inventory record created (FIFO cost of the batch)
        Only ever increases — this is the GROSS all-time-lost figure.

    total_lost_inventory_recovered:
        + previously-lost product marked "found" again (mark_lost_inventory_found)
        Only ever increases too (it's a gross running total, same as every
        other field here) — it does NOT decrement total_lost_inventory_worth.
        The dashboard's displayed "Lost Inventory Worth" is the NET figure
        (total_lost_inventory_worth - total_lost_inventory_recovered),
        computed in get_cashflow_stats(), mirroring how supplier_payable_
        outstanding (net) already sits alongside total_paid_payables (gross).

    total_purchase_returns_value / total_purchase_returns_cogs /
    total_customer_returns_value / total_customer_returns_cogs:
        + purchase/customer return accepted
        No reversal path exists — these fields only ever increase.

    total_invoice_revenue / total_invoice_cogs / total_gross_profit:
        + invoice confirmed (grand_total / total_cogs / gross_profit at that moment)
        Returns do NOT reduce these — confirmed by tracing _recalculate_invoice_totals,
        which sums unreduced InvoiceItem fields regardless of returned_quantity.
        So confirm_invoice is the only place these are ever set — only ever increase.
    """

    # ---- Receivables (from customers) ----
    cash_in_hand             = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                   help_text="Actual cash available: invoice receipts - expenses - supplier payments.")
    total_cash_inflow        = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                   help_text="Sum of every currently-active cash inflow event (same set as get_cash_in_hand_breakdown()'s inflow rows). Decreases on delete/reversal of an inflow — NOT gross-ever. total_cash_inflow - total_cash_outflow always equals cash_in_hand.")
    total_cash_outflow       = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                   help_text="Sum of every currently-active cash outflow event (same set as get_cash_in_hand_breakdown()'s outflow rows). Decreases on delete/reversal of an outflow — NOT gross-ever.")
    customer_outstanding     = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                   help_text="Amount customers still owe us.")
    total_invoices_cash      = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                   help_text="Total cash ever collected from invoice payments (gross, never reduced).")

    # ---- Payables (to suppliers) ----
    total_paid_payables          = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                       help_text="Total cash ever paid to suppliers.")
    supplier_payable_outstanding = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                       help_text="Amount we still owe suppliers.")
    total_purchases_cash         = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                       help_text="Total purchase value: paid + outstanding.")

    # ---- Expenses ----
    total_expenses_amount = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    total_recurring_expenses_paid = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                        help_text="Total ever paid against recurring expense assignments (salaries, rent, ...), all-time. Only ever increases; only moves on payment, never on assignment.")

    # ---- Lost inventory ----
    total_lost_inventory_worth = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                     help_text="Total FIFO cost of all products ever marked lost (gross, only ever increases).")
    total_lost_inventory_recovered = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                     help_text="Total FIFO cost of lost products later marked found (gross, only ever increases). Dashboard shows worth minus this as the net figure.")

    # ---- Returns ----
    total_purchase_returns_value = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                        help_text="Total value of accepted returns to suppliers. Only ever increases.")
    total_purchase_returns_cogs  = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                        help_text="Total pre-tax cost portion (total_return_gross) of accepted returns to suppliers — mirrors total_customer_returns_cogs for dashboard symmetry. Only ever increases.")
    total_customer_returns_value = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                        help_text="Total value of accepted returns from customers. Only ever increases.")
    total_customer_returns_cogs  = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                        help_text="Total COGS reversed via accepted customer returns. Only ever increases.")

    # ---- Profit / margin ----
    total_invoice_revenue = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                help_text="Total grand_total across all confirmed invoices (invoiced amount, not cash received). Only ever increases.")
    total_invoice_cogs    = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                help_text="Total COGS across all confirmed invoices. Only ever increases.")
    total_gross_profit    = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                help_text="Total gross profit across all confirmed invoices. Only ever increases.")

    # ---- Dashboard counts (O(1) — no live COUNT queries) ----
    total_invoices_count  = models.IntegerField(default=0,
                                help_text="Confirmed, non-data-entry invoices. +1 in sync_invoice_confirmed; confirmed invoices are undeletable, so it never decrements.")
    total_purchases_count = models.IntegerField(default=0,
                                help_text="Confirmed, non-data-entry purchase orders. +1 in sync_purchase_order_confirmed; confirmed orders are undeletable, so it never decrements.")
    total_expenses_count  = models.IntegerField(default=0,
                                help_text="Non-deleted expenses. +1 on create_expense, -1 on delete_expense.")

    # ---- Last sync metadata ----
    last_updated_at = models.DateTimeField(auto_now=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="cashflow_updates",
    )

    class Meta:
        verbose_name        = "Cash Flow"
        verbose_name_plural = "Cash Flow"

    def __str__(self):
        return f"CashFlow — cash_in_hand: {self.cash_in_hand}"

    @classmethod
    def get_instance(cls):
        """Always returns the single CashFlow record, creating it if needed."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance