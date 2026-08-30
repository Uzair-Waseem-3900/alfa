from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# CashAdjustment  (ledger — lost/found cash reconciliation, mirrors taxes.TaxPayment)
# ---------------------------------------------------------------------------

class CashAdjustment(models.Model):
    """
    A physical cash discrepancy — lost (theft, miscount, misplaced) or found
    (recovered, surprise cash discovered during counting). Confirmed
    immediately on creation — no draft state. Lost deducts from
    CashFlow.cash_in_hand, found adds to it. Full audit trail via
    created_by/updated_by/deleted_by.

    Lost and found entries are independent — a found entry is never linked
    to or capped by a specific prior lost entry (matches how cash counting
    actually works: you often can't tie a recovery to a specific loss).
    """

    class AdjustmentType(models.TextChoices):
        LOST  = "lost", "Lost"
        FOUND = "found", "Found"

    amount          = models.DecimalField(max_digits=18, decimal_places=4)
    adjustment_type = models.CharField(max_length=10, choices=AdjustmentType.choices)
    adjustment_date = models.DateField(db_index=True)
    reason          = models.TextField(blank=True, default="")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="cash_adjustments_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="cash_adjustments_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="cash_adjustments_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Cash Adjustment"
        verbose_name_plural  = "Cash Adjustments"
        ordering             = ["-adjustment_date", "-created_at"]

    def __str__(self):
        return f"{self.get_adjustment_type_display()} — {self.amount} on {self.adjustment_date}"


# ---------------------------------------------------------------------------
# Investor  (one row per investor — stored running totals, O(1) reads)
# ---------------------------------------------------------------------------

class Investor(models.Model):
    """
    One row per investor. total_invested/total_withdrawn/net_stake are
    stored fields, recalculated and saved by InvestorTransaction services on
    every investment/withdrawal — never computed at read time.

    net_stake is what this investor currently has invested in the business
    (total_invested - total_withdrawn) — REAL cash principal. This is the
    ONLY figure withdrawals are ever validated against.

    growth_rate / current_worth are a separate, purely informational track:
    current_worth is net_stake compounded monthly by growth_rate (see
    cash_management.services._catch_up_investor_growth) — a THEORETICAL
    value, reserved for future profit-sharing calculations once "actual"
    (net, not just gross) profit is tracked. It never gates what an investor
    can withdraw; net_stake alone does that.
    """

    name           = models.CharField(max_length=255)
    contact_number = models.CharField(max_length=50, blank=True, default="")
    email          = models.EmailField(blank=True, default="")
    note           = models.TextField(blank=True, default="")

    total_invested  = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                           help_text="Total ever invested by this investor (gross, only ever increases).")
    total_withdrawn = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                           help_text="Total ever withdrawn by this investor (gross, only ever increases).")
    net_stake       = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                           help_text="total_invested - total_withdrawn. What this investor currently has in the business. The ONLY figure withdrawals are validated against.")

    growth_rate    = models.DecimalField(max_digits=5, decimal_places=4, default=0,
                           help_text="Annual compound growth rate (e.g. 0.02 for 2%), zero or positive only. Editable any time — only affects entries posted after the change.")
    current_worth  = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                           help_text="net_stake compounded monthly by growth_rate — a theoretical value, informational only, never used for withdrawal validation. Forced to exactly 0 when net_stake reaches 0 (full exit).")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="investors_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="investors_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="investors_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Investor"
        verbose_name_plural  = "Investors"
        ordering             = ["name"]

    def __str__(self):
        return f"{self.name} (stake: {self.net_stake})"


# ---------------------------------------------------------------------------
# InvestorTransaction  (ledger — mirrors taxes.TaxPayment)
# ---------------------------------------------------------------------------

class InvestorTransaction(models.Model):
    """
    One investment or withdrawal event for an investor. Confirmed
    immediately on creation — no draft state. Investment adds to
    CashFlow.cash_in_hand, withdrawal deducts from it. A withdrawal is
    rejected if it would exceed the investor's current net_stake (never
    current_worth — see Investor docstring).

    worth_delta is the EXACT change this transaction caused to the
    investor's current_worth: +amount for an investment, -amount for a
    normal withdrawal, or -(current_worth at that moment) for a withdrawal
    that fully exits the investor (net_stake reaches 0) — which wipes any
    residual theoretical growth, not just the withdrawn amount. Storing the
    exact figure here means deleting a transaction can always reverse
    current_worth precisely, including the full-exit case.
    """

    class TransactionType(models.TextChoices):
        INVESTMENT = "investment", "Investment"
        WITHDRAWAL = "withdrawal", "Withdrawal"

    investor         = models.ForeignKey(Investor, on_delete=models.PROTECT, related_name="transactions")
    transaction_type = models.CharField(max_length=12, choices=TransactionType.choices)
    amount           = models.DecimalField(max_digits=18, decimal_places=4)
    worth_delta      = models.DecimalField(max_digits=18, decimal_places=4, default=0,
                            help_text="Exact change applied to current_worth by this transaction — stored so deletion can reverse it precisely.")
    transaction_date = models.DateField(db_index=True)
    note             = models.TextField(blank=True, default="")
    is_data_entry    = models.BooleanField(default=False,
                            help_text="True for pre-go-live investor capital recorded via the Data Entry "
                                       "app — does NOT move CashFlow.cash_in_hand (see data_entry.services).")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="investor_transactions_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="investor_transactions_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="investor_transactions_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Investor Transaction"
        verbose_name_plural  = "Investor Transactions"
        ordering             = ["-transaction_date", "-created_at"]

    def __str__(self):
        return f"{self.get_transaction_type_display()} — {self.amount} ({self.investor.name})"


# ---------------------------------------------------------------------------
# InvestorValuationEntry  (history ledger — mirrors assets.AssetValuationEntry)
# ---------------------------------------------------------------------------

class InvestorValuationEntry(models.Model):
    """
    One row per monthly growth posting for an investor's current_worth.
    Auto-posted by cash_management.services._catch_up_investor_growth —
    never edited or deleted, pure append-only audit trail. rate_applied is
    snapshotted at post time so later growth_rate edits can never rewrite
    history — only entries posted after a rate change use the new rate.
    """

    investor      = models.ForeignKey(Investor, on_delete=models.CASCADE, related_name="valuation_entries")
    period        = models.CharField(max_length=7, db_index=True, help_text="YYYY-MM this entry applies to.")
    rate_applied  = models.DecimalField(max_digits=5, decimal_places=4, help_text="Annual growth rate used for this entry.")
    worth_before  = models.DecimalField(max_digits=20, decimal_places=4)
    worth_after   = models.DecimalField(max_digits=20, decimal_places=4)
    amount        = models.DecimalField(max_digits=20, decimal_places=4,
                                          help_text="worth_after - worth_before. Zero or positive — growth only, per the confirmed design.")
    note          = models.TextField(blank=True, default="")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="investor_valuation_entries_created",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Investor Valuation Entry"
        verbose_name_plural  = "Investor Valuation Entries"
        ordering             = ["-period", "-created_at"]
        indexes = [
            models.Index(fields=["investor", "-period"], name="idx_investor_valuation_lookup"),
        ]
        constraints = [
            # Two concurrent catch-up runs (e.g. two stats requests at a
            # month boundary) could otherwise both post the same month for
            # the same investor — the DB now makes that physically
            # impossible; _catch_up_investor_growth treats the violation as
            # "someone else already posted" and stops cleanly.
            models.UniqueConstraint(
                fields=["investor", "period"], name="uniq_investor_valuation_period",
            ),
        ]

    def __str__(self):
        return f"{self.investor.name} — growth {self.period}: {self.amount}"


# ---------------------------------------------------------------------------
# OwnerTransaction  (ledger — owner drawings/contributions, mirrors InvestorTransaction)
# ---------------------------------------------------------------------------

class OwnerTransaction(models.Model):
    """
    One contribution or drawing event for the business owner. Distinct from
    Investor/InvestorTransaction (external investor equity) and from
    CashAdjustment (unexplained physical cash discrepancies) — this is the
    owner deliberately putting personal money in, or deliberately taking
    money out for personal use. Confirmed immediately on creation — no draft
    state. Contribution adds to CashFlow.cash_in_hand, drawing deducts from
    it.

    Unlike InvestorTransaction, a drawing is NOT capped by net_owner_capital
    — a sole owner can draw out more than they've contributed (financed by
    the business's profits), same as any real owner's drawing account. It's
    normal for net_owner_capital to go negative.

    Only one implicit "owner" for now (no separate Owner model, unlike
    Investor) — this store has a single owner. If that ever changes,
    this would need to grow an Owner FK the same way InvestorTransaction has one.
    """

    class TransactionType(models.TextChoices):
        CONTRIBUTION = "contribution", "Contribution"
        DRAWING      = "drawing", "Drawing"

    transaction_type = models.CharField(max_length=12, choices=TransactionType.choices)
    amount           = models.DecimalField(max_digits=18, decimal_places=4)
    transaction_date = models.DateField(db_index=True)
    note             = models.TextField(blank=True, default="")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="owner_transactions_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="owner_transactions_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="owner_transactions_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Owner Transaction"
        verbose_name_plural  = "Owner Transactions"
        ordering             = ["-transaction_date", "-created_at"]

    def __str__(self):
        return f"{self.get_transaction_type_display()} — {self.amount} on {self.transaction_date}"


# ---------------------------------------------------------------------------
# CashManagementFlow  (singleton — mirrors cash_flow.CashFlow / taxes.TaxFlow)
# ---------------------------------------------------------------------------

class CashManagementFlow(models.Model):
    """
    Single live record — O(1) dashboard reads. Never created manually —
    managed exclusively via cash_management.services. Updated atomically
    whenever a CashAdjustment or InvestorTransaction is created/deleted.

    net_cash_lost / net_investor_capital are stored fields, recalculated and
    SAVED (not just computed on read) on every sync — same discipline as
    taxes.TaxFlow.net_sales_tax_payable.
    """

    total_cash_lost      = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                help_text="Total cash ever recorded as lost, all-time (gross, only ever increases).")
    total_cash_recovered = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                help_text="Total cash ever recorded as found/recovered, all-time (gross, only ever increases).")
    net_cash_lost         = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                help_text="total_cash_lost - total_cash_recovered, floored at 0. Stored, recalculated on every sync.")

    total_investor_capital   = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                   help_text="Total ever invested by all investors, all-time (gross, only ever increases).")
    total_investor_withdrawn = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                   help_text="Total ever withdrawn by all investors, all-time (gross, only ever increases).")
    net_investor_capital     = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                   help_text="total_investor_capital - total_investor_withdrawn. Current total equity capital in the business. Stored, recalculated on every sync.")
    total_investor_net_worth = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                   help_text="Sum of every investor's current_worth (theoretical, growth-compounded value). Informational only — never used for withdrawal validation.")

    total_owner_contributions   = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                       help_text="Total cash the owner has deposited into the business, all-time (gross, only ever increases).")
    total_owner_drawings        = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                       help_text="Total cash the owner has withdrawn for personal use, all-time (gross, only ever increases).")
    total_owner_contributions_count = models.PositiveIntegerField(default=0,
                                       help_text="Count of owner contribution transactions, all-time (only ever increases).")
    total_owner_withdrawals_count = models.PositiveIntegerField(default=0,
                                       help_text="Count of owner drawing transactions, all-time (only ever increases).")
    net_owner_capital            = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                       help_text="total_owner_contributions - total_owner_drawings. NOT floored at 0 — "
                                                  "a sole owner can draw out more than they've deposited, financed by "
                                                  "the business's profits, same as any real owner's drawing account.")

    growth_caught_up_through = models.CharField(max_length=7, blank=True, default="",
                                    help_text="YYYY-MM through which EVERY investor's growth is posted. Growth only "
                                              "becomes due at month boundaries, so while this equals the current month "
                                              "the per-investor catch-up loop can be skipped entirely (O(1) staleness "
                                              "check — same throttle pattern as users.TokenFlushState).")

    last_updated_at = models.DateTimeField(auto_now=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="cash_management_flow_updates",
    )

    class Meta:
        verbose_name        = "Cash Management Flow"
        verbose_name_plural  = "Cash Management Flow"

    def __str__(self):
        return f"CashManagementFlow — net_cash_lost: {self.net_cash_lost}, net_investor_capital: {self.net_investor_capital}"

    @classmethod
    def get_instance(cls):
        """Always returns the single CashManagementFlow record, creating it if needed."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance
