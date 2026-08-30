from django.conf import settings
from django.db import models

# NOTE: Business Worth (see selectors.get_business_worth/get_ownership_split)
# still has no stored model — it's a live aggregation of other apps' already
# O(1) figures. Monthly Profit is different: it's a point-in-time snapshot
# of a FINISHED month's own activity, which must be frozen forever (the
# whole point of "store, don't calculate at runtime" here), so it gets real
# models below.


# ---------------------------------------------------------------------------
# MonthlyProfit  (one row per FINISHED month — never recomputed once created)
# ---------------------------------------------------------------------------

class MonthlyProfit(models.Model):
    """
    One row per finished month, created once by
    profits.services.catch_up_monthly_profits (catch-up on read, no cron —
    same pattern as assets/recurring_expenses) and never recomputed
    afterward. The current, still-accumulating month deliberately has no
    row here — profits.selectors.get_current_month_profit() computes it
    live and marks it provisional.

    net_profit = net_gross_profit minus every deduction below, plus every
    addition, plus disposal_gain_loss (itself signed — a loss is already
    negative, so it's ADDED, not subtracted). Not floored at 0 — a month
    with heavy losses can legitimately show negative net profit, same "not
    floored" convention as the Profit/Margin Report.

    Lost/found cash and lost/found inventory are stored as four SEPARATE
    figures, not netted against each other before storage — each is an
    honest, independently-dated fact for this specific month (mirrors how
    CashAdjustment already tracks LOST/FOUND as two dated event types).
    A June loss stays in June forever; a July recovery of that June loss
    shows up as July's found_inventory and adds to July's profit — nothing
    is silently absorbed into the month the original loss happened in.
    See purchases.models.LostInventoryRecovery for the dated ledger this
    relies on for the inventory side (CashAdjustment already had this for cash).
    """

    period = models.CharField(max_length=7, unique=True, db_index=True, help_text="YYYY-MM")

    # ---- Gross figures (before returns) — same numbers as the Gross Profit Trend chart ----
    gross_revenue = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    gross_cogs    = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    gross_profit  = models.DecimalField(max_digits=20, decimal_places=4, default=0)

    # ---- Net of returns accepted this month ----
    net_revenue      = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    net_cogs         = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    net_gross_profit = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                            help_text="net_revenue - net_cogs — the starting point for net_profit below.")

    # ---- Deductions, each a cash-basis figure for THIS month specifically ----
    expenses_paid           = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    recurring_expenses_paid = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    gst_paid                 = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    wht_paid                 = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    lost_cash        = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                            help_text="Cash marked lost this month (CashAdjustment LOST events dated this month).")
    found_cash        = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                            help_text="Cash marked found this month (CashAdjustment FOUND events dated this month) — added to profit.")
    lost_inventory     = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                            help_text="FIFO cost of inventory lost this month (LostInventoryRecord created this month).")
    found_inventory    = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                            help_text="Value of inventory recovered this month (LostInventoryRecovery dated this month, regardless of when originally lost) — added to profit.")
    depreciation              = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                    help_text="Sum of AssetValuationEntry depreciation posted for this period.")
    disposal_gain_loss        = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                    help_text="Signed — positive for a net gain on asset disposals this month, negative for a net loss. Added, not subtracted.")

    net_profit = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                    help_text="The 'real profit' for this month — net_gross_profit minus every deduction above, plus disposal_gain_loss.")

    # ---- Ownership split, snapshotted at finalization ----
    total_investor_share_percent = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    total_investor_share_amount  = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    owner_share_percent           = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    owner_share_amount            = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                        help_text="The exact remainder: net_profit - total_investor_share_amount. "
                                                   "Settled the same way as an investor share — see MonthlyProfitOwnerShare.")

    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Monthly Profit"
        verbose_name_plural  = "Monthly Profits"
        ordering             = ["-period"]

    def __str__(self):
        return f"{self.period} — net profit {self.net_profit}"


# ---------------------------------------------------------------------------
# MonthlyProfitInvestorShare  (one row per investor per finished month)
# ---------------------------------------------------------------------------

class MonthlyProfitInvestorShare(models.Model):
    """
    One investor's slice of one month's net_profit. share_percent_snapshot
    is frozen forever at creation time — it is that investor's ownership %
    AS OF that month, never recalculated even if their current ownership %
    later changes (new investment, growth compounding, etc.).

    amount_paid_out / amount_reinvested are updated exclusively by
    InvestorProfitPayout rows via profits.services — never edited directly.
    Settling is entirely optional: an unpaid or partially-paid balance is
    NOT a liability anywhere in this system (not in Business Worth, not
    anywhere else) — it's pure record-keeping for the owner's own tracking,
    not a debt the business owes.
    """

    class PaymentStatus(models.TextChoices):
        UNPAID  = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partial"
        PAID    = "paid", "Paid"

    monthly_profit = models.ForeignKey(MonthlyProfit, on_delete=models.CASCADE, related_name="investor_shares")
    investor       = models.ForeignKey("cash_management.Investor", on_delete=models.PROTECT, related_name="monthly_profit_shares")
    investor_name_snapshot = models.CharField(max_length=255)

    share_percent_snapshot = models.DecimalField(max_digits=10, decimal_places=4,
                                help_text="This investor's ownership %% as of this month — frozen forever.")
    share_amount = models.DecimalField(max_digits=20, decimal_places=4, default=0)

    amount_paid_out   = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    amount_reinvested = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    payment_status    = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID, db_index=True)

    class Meta:
        verbose_name        = "Monthly Profit Investor Share"
        verbose_name_plural  = "Monthly Profit Investor Shares"
        ordering             = ["monthly_profit", "investor_name_snapshot"]
        constraints = [
            models.UniqueConstraint(fields=["monthly_profit", "investor"], name="unique_investor_share_per_month"),
        ]

    @property
    def amount_settled(self):
        return self.amount_paid_out + self.amount_reinvested

    @property
    def amount_remaining(self):
        return self.share_amount - self.amount_settled

    def __str__(self):
        return f"{self.monthly_profit.period} — {self.investor_name_snapshot}: {self.share_amount}"


# ---------------------------------------------------------------------------
# MonthlyProfitOwnerShare  (one row per finished month — mirrors MonthlyProfitInvestorShare)
# ---------------------------------------------------------------------------

class MonthlyProfitOwnerShare(models.Model):
    """
    The owner's slice of one month's net_profit — structurally identical to
    MonthlyProfitInvestorShare (same amount_paid_out/amount_reinvested/
    payment_status shape, settled via OwnerProfitPayout the same way an
    investor share is settled via InvestorProfitPayout), except there's
    exactly one per month (OneToOne, not FK — only one owner, unlike
    investors) and no percent snapshot of its own (owner_share_percent
    already lives on MonthlyProfit).

    Created automatically — either inside _finalize_month for new months, or
    self-healing backfilled by catch_up_monthly_profits() for any existing
    MonthlyProfit row that predates this model (from its own already-stored
    owner_share_amount, so no recomputation, no drift).
    """

    class PaymentStatus(models.TextChoices):
        UNPAID  = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partial"
        PAID    = "paid", "Paid"

    monthly_profit = models.OneToOneField(MonthlyProfit, on_delete=models.CASCADE, related_name="owner_share")

    share_amount = models.DecimalField(max_digits=20, decimal_places=4, default=0)

    amount_paid_out   = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    amount_reinvested = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    payment_status    = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID, db_index=True)

    class Meta:
        verbose_name        = "Monthly Profit Owner Share"
        verbose_name_plural  = "Monthly Profit Owner Shares"
        ordering             = ["-monthly_profit__period"]

    @property
    def amount_settled(self):
        return self.amount_paid_out + self.amount_reinvested

    @property
    def amount_remaining(self):
        return self.share_amount - self.amount_settled

    def __str__(self):
        return f"{self.monthly_profit.period} — Owner: {self.share_amount}"


# ---------------------------------------------------------------------------
# InvestorProfitPayout  (ledger — mirrors taxes.TaxPayment / purchases.SupplierPayment)
# ---------------------------------------------------------------------------

class InvestorProfitPayout(models.Model):
    """
    One settlement action against an investor's monthly profit share.
    PAYOUT moves cash_in_hand out and never touches the investor's capital
    account (net_stake/current_worth) — it's a distribution of earnings,
    not a return of capital. REINVEST does the same cash-out, then
    immediately creates a real cash_management.InvestorTransaction
    (INVESTMENT) that brings the cash back in AND genuinely grows the
    investor's capital account — linked_investor_transaction points at
    that row so the two are never orphaned from each other. Net cash_in_hand
    effect for a reinvest is zero, but as two honest, separately reversible
    ledger entries — not a single flag on one row.
    """

    class ActionType(models.TextChoices):
        PAYOUT   = "payout", "Payout"
        REINVEST = "reinvest", "Reinvest"

    share       = models.ForeignKey(MonthlyProfitInvestorShare, on_delete=models.PROTECT, related_name="payouts")
    amount      = models.DecimalField(max_digits=18, decimal_places=4)
    payout_date = models.DateField(db_index=True)
    action_type = models.CharField(max_length=10, choices=ActionType.choices)
    note        = models.TextField(blank=True, default="")

    linked_investor_transaction = models.ForeignKey(
        "cash_management.InvestorTransaction", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="linked_profit_payout",
        help_text="Set only when action_type='reinvest' — the InvestorTransaction that brought the cash back in.",
    )

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="investor_profit_payouts_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="investor_profit_payouts_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="investor_profit_payouts_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Investor Profit Payout"
        verbose_name_plural  = "Investor Profit Payouts"
        ordering             = ["-payout_date", "-created_at"]

    def __str__(self):
        return f"{self.get_action_type_display()} — {self.amount} on {self.payout_date}"


# ---------------------------------------------------------------------------
# OwnerProfitPayout  (ledger — mirrors InvestorProfitPayout)
# ---------------------------------------------------------------------------

class OwnerProfitPayout(models.Model):
    """
    One settlement action against the owner's monthly profit share. Exact
    mirror of InvestorProfitPayout: PAYOUT moves cash_in_hand out only.
    REINVEST does the same cash-out, then immediately creates a real
    cash_management.OwnerTransaction (CONTRIBUTION) that brings the cash
    back in — linked_owner_transaction points at that row so the two are
    never orphaned. Net cash_in_hand effect for a reinvest is zero, but as
    two honest, separately reversible ledger entries.
    """

    class ActionType(models.TextChoices):
        PAYOUT   = "payout", "Payout"
        REINVEST = "reinvest", "Reinvest"

    owner_share = models.ForeignKey(MonthlyProfitOwnerShare, on_delete=models.PROTECT, related_name="payouts")
    amount      = models.DecimalField(max_digits=18, decimal_places=4)
    payout_date = models.DateField(db_index=True)
    action_type = models.CharField(max_length=10, choices=ActionType.choices)
    note        = models.TextField(blank=True, default="")

    linked_owner_transaction = models.ForeignKey(
        "cash_management.OwnerTransaction", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="linked_profit_payout",
        help_text="Set only when action_type='reinvest' — the OwnerTransaction that brought the cash back in.",
    )

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="owner_profit_payouts_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="owner_profit_payouts_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="owner_profit_payouts_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Owner Profit Payout"
        verbose_name_plural  = "Owner Profit Payouts"
        ordering             = ["-payout_date", "-created_at"]

    def __str__(self):
        return f"{self.get_action_type_display()} — {self.amount} on {self.payout_date}"


# ---------------------------------------------------------------------------
# ProfitFlow  (singleton — mirrors CashFlow/TaxFlow/AssetFlow/RecurringExpenseFlow)
# ---------------------------------------------------------------------------

class ProfitFlow(models.Model):
    """
    Single live record — O(1) dashboard reads. Never created manually —
    managed exclusively via profits.services, updated whenever a month is
    finalized or a payout is created/deleted. total_net_profit /
    total_investor_profit_share / total_owner_profit_share are NOT floored
    at 0 — a run of loss months can legitimately make lifetime profit
    negative, same "not floored" convention as the Profit/Margin Report.
    """

    total_gross_profit             = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                          help_text="Sum of gross_profit across every FINALIZED month only — excludes the current, still-open month.")
    total_net_gross_profit         = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                          help_text="Sum of net_gross_profit (after returns) across every finalized month.")
    total_net_profit              = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    total_investor_profit_share   = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    total_owner_profit_share      = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    total_paid_out_to_investors    = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                          help_text="All-time, gross, only ever increases.")
    total_reinvested_by_investors  = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                          help_text="All-time, gross, only ever increases.")
    total_paid_out_to_owner        = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                          help_text="All-time, gross, only ever increases.")
    total_reinvested_by_owner      = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                          help_text="All-time, gross, only ever increases.")
    months_finalized_count        = models.PositiveIntegerField(default=0)

    last_updated_at = models.DateTimeField(auto_now=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="profit_flow_updates",
    )

    class Meta:
        verbose_name        = "Profit Flow"
        verbose_name_plural  = "Profit Flow"

    def __str__(self):
        return f"ProfitFlow — total_net_profit: {self.total_net_profit}"

    @classmethod
    def get_instance(cls):
        """Always returns the single ProfitFlow record, creating it if needed."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance
