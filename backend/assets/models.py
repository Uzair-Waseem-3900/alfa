from django.conf import settings
from django.db import models


# ---------------------------------------------------------------------------
# AssetCategory
# ---------------------------------------------------------------------------

class AssetCategory(models.Model):
    """
    valuation_method is set once at creation and is PERMANENTLY LOCKED after
    that — never changeable via update_asset_category. Switching a category
    between depreciation/revaluation mid-life would corrupt the meaning of
    every AssetValuationEntry already posted under it, so it's simply not a
    supported operation.

    depreciation_rate IS editable any time — but editing it only affects
    AssetValuationEntry rows posted from that point forward. Every entry
    snapshots the rate it actually used (rate_applied), so past entries are
    immune to later rate changes. See assets/services.py.
    """

    class ValuationMethod(models.TextChoices):
        DEPRECIATION = "depreciation", "Depreciation"
        REVALUATION  = "revaluation", "Revaluation"
        NONE         = "none", "None (never changes)"

    name              = models.CharField(max_length=255, unique=True)
    valuation_method  = models.CharField(max_length=12, choices=ValuationMethod.choices)
    depreciation_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=0,
        help_text="Annual reducing-balance rate (e.g. 0.15 for 15%). Only meaningful "
                   "when valuation_method is 'depreciation'. Editable any time — only "
                   "affects entries posted after the change.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="asset_categories_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Asset Category"
        verbose_name_plural  = "Asset Categories"
        ordering             = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_valuation_method_display()})"


# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------

class Asset(models.Model):
    """
    current_worth is a stored field — O(1) to read, always reflects the
    latest posted AssetValuationEntry. Never recomputed from scratch on
    read; only ever updated by assets.services (catch-up depreciation,
    manual revaluation, or disposal).

    acquisition_type:
        existing — already owned before being registered. No cash movement.
                   Full historical AssetValuationEntry rows are back-filled
                   from acquisition_date to today at creation time.
        new      — purchased right now. cash_in_hand decreases by cost via
                   cash_flow.services.sync_asset_purchased.
    """

    class AcquisitionType(models.TextChoices):
        EXISTING = "existing", "Existing"
        NEW      = "new", "New"

    name             = models.CharField(max_length=255)
    category         = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name="assets")
    acquisition_type = models.CharField(max_length=10, choices=AcquisitionType.choices)
    cost             = models.DecimalField(max_digits=18, decimal_places=4)
    acquisition_date = models.DateField(db_index=True)
    current_worth    = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    note             = models.TextField(blank=True, default="")

    is_disposed = models.BooleanField(default=False, db_index=True)

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="assets_created",
    )
    updated_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="assets_updated",
    )
    deleted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assets_deleted",
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    deleted_at  = models.DateTimeField(null=True, blank=True)
    is_deleted  = models.BooleanField(default=False, db_index=True)

    objects     = models.Manager()

    class Meta:
        verbose_name        = "Asset"
        verbose_name_plural  = "Assets"
        ordering             = ["-acquisition_date", "-created_at"]

    def __str__(self):
        return f"{self.name} (worth: {self.current_worth})"


# ---------------------------------------------------------------------------
# AssetValuationEntry  (history ledger — immutable once posted)
# ---------------------------------------------------------------------------

class AssetValuationEntry(models.Model):
    """
    One row per applied change to an asset's worth — depreciation (auto-
    posted by catch-up, see assets.services._catch_up_asset_depreciation) or
    revaluation (posted manually by an admin). Never edited or deleted —
    pure append-only audit trail. rate_applied is snapshotted at post time
    so later category rate edits can never rewrite history.
    """

    class EntryType(models.TextChoices):
        DEPRECIATION = "depreciation", "Depreciation"
        REVALUATION  = "revaluation", "Revaluation"

    asset         = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="valuation_entries")
    entry_type    = models.CharField(max_length=12, choices=EntryType.choices)
    period        = models.CharField(max_length=7, db_index=True, help_text="YYYY-MM this entry applies to.")
    rate_applied  = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True,
                                          help_text="Depreciation rate used for this entry. Null for revaluations.")
    worth_before  = models.DecimalField(max_digits=18, decimal_places=4)
    worth_after   = models.DecimalField(max_digits=18, decimal_places=4)
    amount        = models.DecimalField(max_digits=18, decimal_places=4,
                                          help_text="worth_after - worth_before. Negative for depreciation, either sign for revaluation.")
    note          = models.TextField(blank=True, default="")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="asset_valuation_entries_created",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Asset Valuation Entry"
        verbose_name_plural  = "Asset Valuation Entries"
        ordering             = ["-period", "-created_at"]
        indexes = [
            models.Index(fields=["asset", "entry_type", "-period"], name="idx_asset_valuation_lookup"),
        ]
        constraints = [
            # Two concurrent catch-up runs at a month boundary could otherwise
            # both post the same depreciation month for the same asset —
            # the DB now makes that physically impossible. DEPRECIATION only:
            # multiple manual REVALUATIONS in one month are legitimate.
            models.UniqueConstraint(
                fields=["asset", "period"],
                condition=models.Q(entry_type="depreciation"),
                name="uniq_asset_depreciation_period",
            ),
        ]

    def __str__(self):
        return f"{self.asset.name} — {self.get_entry_type_display()} {self.period}: {self.amount}"


# ---------------------------------------------------------------------------
# AssetDisposal  (audit trail of exit — scrapped or sold)
# ---------------------------------------------------------------------------

class AssetDisposal(models.Model):
    """
    Records why and how an asset left the system. Scrapped: no cash
    movement, just a note. Sold: cash_in_hand increases by sale_amount and
    gain_loss = sale_amount - worth_at_disposal is computed and stored.
    """

    class DisposalType(models.TextChoices):
        SCRAPPED = "scrapped", "Scrapped"
        SOLD     = "sold", "Sold"

    asset             = models.OneToOneField(Asset, on_delete=models.CASCADE, related_name="disposal")
    disposal_type     = models.CharField(max_length=10, choices=DisposalType.choices)
    disposal_date     = models.DateField(db_index=True)
    sale_amount       = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    worth_at_disposal = models.DecimalField(max_digits=18, decimal_places=4,
                                              help_text="Asset's current_worth snapshotted at the moment of disposal.")
    gain_loss         = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True,
                                              help_text="sale_amount - worth_at_disposal. Null for scrapped assets.")
    reason            = models.TextField(blank=True, default="")

    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="asset_disposals_created",
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Asset Disposal"
        verbose_name_plural  = "Asset Disposals"
        ordering             = ["-disposal_date", "-created_at"]

    def __str__(self):
        return f"{self.asset.name} — {self.get_disposal_type_display()} on {self.disposal_date}"


# ---------------------------------------------------------------------------
# AssetPayment  (event table — one row per real cash-moving asset event)
# ---------------------------------------------------------------------------

class AssetPayment(models.Model):
    """
    One row per real cash-moving asset event: a "new" acquisition (outflow,
    written by assets.services.create_asset) or a "sold" disposal (inflow,
    written by assets.services.dispose_asset). Written once, at creation
    time, right next to payment_methods.services.record_allocations for
    that same event — same "only this code writes it" convention as
    cash_flow.CashMovement.

    Exists so GET /assets/payments/ can list purchases+sales in ONE indexed,
    paginated query instead of live-merging Asset and AssetDisposal in
    Python on every request (architecture.md: a multi-source drill-down view
    needs an event table, not a per-request cross-model merge).

    source_model/source_id key back into payment_methods.PaymentAllocation
    for the real per-method split — they snapshot which original row
    (assets.asset or assets.assetdisposal) record_allocations was called
    against, since that's a DIFFERENT object than `asset` for sale rows.

    Neither Asset nor AssetDisposal support edit/delete after creation
    (confirmed in assets.services — no update_asset/delete_asset path), so
    this table is create-only: no soft-delete/reverse/refresh path needed,
    same reasoning as AssetDisposal itself having none.
    """

    class PaymentType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        SALE     = "sale", "Sale"

    class Direction(models.TextChoices):
        INFLOW  = "inflow", "Inflow"
        OUTFLOW = "outflow", "Outflow"

    asset        = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="payments")
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices)
    direction    = models.CharField(max_length=10, choices=Direction.choices)
    amount       = models.DecimalField(max_digits=18, decimal_places=4)
    date         = models.DateField(db_index=True)

    source_model = models.CharField(max_length=60, help_text="app_label.model_name of the row that caused this payment (assets.asset or assets.assetdisposal).")
    source_id    = models.BigIntegerField()

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="asset_payments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Asset Payment"
        verbose_name_plural  = "Asset Payments"
        ordering             = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["-date", "-created_at"], name="idx_assetpayment_date"),
            models.Index(fields=["payment_type", "-date"], name="idx_assetpayment_type_date"),
        ]

    def __str__(self):
        return f"{self.asset.name} — {self.get_payment_type_display()} {self.amount}"


# ---------------------------------------------------------------------------
# AssetFlow  (singleton — mirrors cash_flow.CashFlow / taxes.TaxFlow / cash_management.CashManagementFlow)
# ---------------------------------------------------------------------------

class AssetFlow(models.Model):
    """
    Single live record — O(1) dashboard/report-header reads. Never created
    manually — managed exclusively via assets.services. Refreshed by
    catch-up depreciation logic on every read (see assets.selectors.
    get_asset_stats), so it's always current even with no background jobs.
    """

    total_asset_cost              = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                         help_text="Sum of cost across all active (non-disposed) assets.")
    total_current_worth           = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                         help_text="Sum of current_worth across all active (non-disposed) assets.")
    total_accumulated_depreciation = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                         help_text="total_asset_cost - total_current_worth, for depreciation-method assets only.")
    total_disposed_count          = models.PositiveIntegerField(default=0)
    total_gain_on_disposal        = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                         help_text="Sum of positive gain_loss across all sold disposals (gross).")
    total_loss_on_disposal        = models.DecimalField(max_digits=20, decimal_places=4, default=0,
                                         help_text="Sum of absolute negative gain_loss across all sold disposals (gross).")

    depreciation_caught_up_through = models.CharField(max_length=7, blank=True, default="",
                                        help_text="YYYY-MM through which EVERY active asset's depreciation is posted. "
                                                  "Depreciation only becomes due at month boundaries, so while this equals "
                                                  "the current month the per-asset catch-up loop can be skipped entirely "
                                                  "(O(1) staleness check — same pattern as CashManagementFlow."
                                                  "growth_caught_up_through). Reset to '' by update_asset_category on a "
                                                  "rate change so the new rate takes effect on the very next read.")

    last_updated_at = models.DateTimeField(auto_now=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="asset_flow_updates",
    )

    class Meta:
        verbose_name        = "Asset Flow"
        verbose_name_plural  = "Asset Flow"

    def __str__(self):
        return f"AssetFlow — total_current_worth: {self.total_current_worth}"

    @classmethod
    def get_instance(cls):
        """Always returns the single AssetFlow record, creating it if needed."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance
