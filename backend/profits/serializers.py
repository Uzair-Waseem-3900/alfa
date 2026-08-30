from rest_framework import serializers

from payment_methods.serializers import MethodAllocationInputSerializer

from .models import (
    InvestorProfitPayout, MonthlyProfit, MonthlyProfitInvestorShare,
    MonthlyProfitOwnerShare, OwnerProfitPayout,
)


class InvestorShareSerializer(serializers.Serializer):
    id            = serializers.IntegerField()
    name          = serializers.CharField()
    current_worth = serializers.DecimalField(max_digits=20, decimal_places=4)
    share_percent = serializers.DecimalField(max_digits=10, decimal_places=4)


class OwnershipSplitSerializer(serializers.Serializer):
    # Business worth breakdown — every component broken out so the total is
    # explainable, not a black box.
    cash_in_hand                 = serializers.DecimalField(max_digits=20, decimal_places=4)
    inventory_value              = serializers.DecimalField(max_digits=20, decimal_places=4)
    assets_current_worth         = serializers.DecimalField(max_digits=20, decimal_places=4)
    customer_outstanding         = serializers.DecimalField(max_digits=20, decimal_places=4)
    supplier_payable_outstanding = serializers.DecimalField(max_digits=20, decimal_places=4)
    sales_tax_outstanding        = serializers.DecimalField(max_digits=20, decimal_places=4)
    wht_outstanding              = serializers.DecimalField(max_digits=20, decimal_places=4)
    recurring_expense_pending    = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_business_worth         = serializers.DecimalField(max_digits=20, decimal_places=4)

    # Ownership split
    total_investor_net_worth = serializers.DecimalField(max_digits=20, decimal_places=4)
    investors                 = InvestorShareSerializer(many=True)
    owner_worth                = serializers.DecimalField(max_digits=20, decimal_places=4)
    owner_share_percent        = serializers.DecimalField(max_digits=10, decimal_places=4)


# ---------------------------------------------------------------------------
# Monthly Profit
# ---------------------------------------------------------------------------

class InvestorProfitPayoutReadSerializer(serializers.ModelSerializer):
    created_by  = serializers.StringRelatedField(read_only=True)
    allocations = serializers.SerializerMethodField()

    class Meta:
        model  = InvestorProfitPayout
        fields = [
            "id", "amount", "payout_date", "action_type", "note", "allocations",
            "linked_investor_transaction", "created_by", "created_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        from payment_methods.serializers import PaymentAllocationReadSerializer

        # Prefer the batch-prefetched map (nested/list contexts — see
        # MonthlyProfitDetailView) over a live per-object query, which
        # would N+1 across every payout in a share's history.
        prefetched = self.context.get("investor_payout_allocations")
        if prefetched is not None:
            rows = prefetched.get(obj.id, [])
        else:
            from payment_methods.selectors import get_allocations_for_source
            rows = get_allocations_for_source(obj)
        return PaymentAllocationReadSerializer(rows, many=True).data


class InvestorProfitPayoutDetailSerializer(serializers.ModelSerializer):
    """
    GET /profits/payouts/<pk>/ only — deliberately NOT reused by
    InvestorProfitPayoutReadSerializer's nested `payouts` field on
    MonthlyProfitInvestorShareSerializer (see profits.selectors.
    get_monthly_profit_by_period's Prefetch, which does not select_related
    "share__monthly_profit" — adding investor_name/period there would
    silently reintroduce a per-payout N+1 in an already-optimized view).
    get_investor_profit_payout_by_id already select_related's
    "share__monthly_profit"/"share__investor" for the single-object case
    this serializer is used in, so these extra fields cost no extra query.
    """
    created_by    = serializers.StringRelatedField(read_only=True)
    allocations   = serializers.SerializerMethodField()
    investor_name = serializers.CharField(source="share.investor_name_snapshot", read_only=True)
    period        = serializers.CharField(source="share.monthly_profit.period", read_only=True)
    share         = serializers.IntegerField(source="share_id", read_only=True)

    class Meta:
        model  = InvestorProfitPayout
        fields = [
            "id", "share", "investor_name", "period", "amount", "payout_date",
            "action_type", "note", "allocations", "linked_investor_transaction",
            "created_by", "created_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        from payment_methods.selectors import get_allocations_for_source
        from payment_methods.serializers import PaymentAllocationReadSerializer
        return PaymentAllocationReadSerializer(get_allocations_for_source(obj), many=True).data


class InvestorProfitPayoutListItemSerializer(serializers.ModelSerializer):
    investor_name = serializers.CharField(source="share.investor_name_snapshot", read_only=True)
    period        = serializers.CharField(source="share.monthly_profit.period", read_only=True)
    created_by    = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = InvestorProfitPayout
        fields = [
            "id", "investor_name", "period", "amount", "payout_date",
            "action_type", "note", "created_by", "created_at",
        ]
        read_only_fields = fields


class InvestorProfitPayoutWriteSerializer(serializers.Serializer):
    amount              = serializers.DecimalField(max_digits=18, decimal_places=4)
    action_type         = serializers.ChoiceField(choices=InvestorProfitPayout.ActionType.choices)
    payout_date         = serializers.DateField()
    method_allocations  = MethodAllocationInputSerializer(
        many=True, required=False,
        help_text="Required when action_type=payout. Not used for reinvest — both legs default silently to Cash.",
    )
    note         = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate(self, attrs):
        if attrs.get("action_type") == InvestorProfitPayout.ActionType.PAYOUT and not attrs.get("method_allocations"):
            raise serializers.ValidationError(
                {"method_allocations": "At least one method must be selected for a payout."}
            )
        return attrs


class MonthlyProfitInvestorShareSerializer(serializers.ModelSerializer):
    amount_settled   = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True)
    amount_remaining = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True)
    payouts          = InvestorProfitPayoutReadSerializer(many=True, read_only=True)

    class Meta:
        model  = MonthlyProfitInvestorShare
        fields = [
            "id", "investor", "investor_name_snapshot", "share_percent_snapshot",
            "share_amount", "amount_paid_out", "amount_reinvested",
            "amount_settled", "amount_remaining", "payment_status", "payouts",
        ]
        read_only_fields = fields

    # Non-deleted, display-ordered payouts come from the selector's filtered
    # Prefetch (get_monthly_profit_by_period) — the declared `payouts` field
    # reads that prefetched cache directly. The old to_representation
    # re-filter here discarded the prefetch and re-queried once per share.


class OwnerProfitPayoutReadSerializer(serializers.ModelSerializer):
    created_by  = serializers.StringRelatedField(read_only=True)
    allocations = serializers.SerializerMethodField()

    class Meta:
        model  = OwnerProfitPayout
        fields = [
            "id", "amount", "payout_date", "action_type", "note", "allocations",
            "linked_owner_transaction", "created_by", "created_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        from payment_methods.serializers import PaymentAllocationReadSerializer

        # Prefer the batch-prefetched map (nested/list contexts — see
        # MonthlyProfitDetailView) over a live per-object query, which
        # would N+1 across every payout in a share's history.
        prefetched = self.context.get("owner_payout_allocations")
        if prefetched is not None:
            rows = prefetched.get(obj.id, [])
        else:
            from payment_methods.selectors import get_allocations_for_source
            rows = get_allocations_for_source(obj)
        return PaymentAllocationReadSerializer(rows, many=True).data


class OwnerProfitPayoutListItemSerializer(serializers.ModelSerializer):
    period     = serializers.CharField(source="owner_share.monthly_profit.period", read_only=True)
    created_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = OwnerProfitPayout
        fields = [
            "id", "period", "amount", "payout_date",
            "action_type", "note", "created_by", "created_at",
        ]
        read_only_fields = fields


class OwnerProfitPayoutWriteSerializer(serializers.Serializer):
    amount              = serializers.DecimalField(max_digits=18, decimal_places=4)
    action_type         = serializers.ChoiceField(choices=OwnerProfitPayout.ActionType.choices)
    payout_date         = serializers.DateField()
    method_allocations  = MethodAllocationInputSerializer(
        many=True, required=False,
        help_text="Required when action_type=payout. Not used for reinvest — both legs default silently to Cash.",
    )
    note         = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate(self, attrs):
        if attrs.get("action_type") == OwnerProfitPayout.ActionType.PAYOUT and not attrs.get("method_allocations"):
            raise serializers.ValidationError(
                {"method_allocations": "At least one method must be selected for a payout."}
            )
        return attrs


class MonthlyProfitOwnerShareSerializer(serializers.ModelSerializer):
    amount_settled   = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True)
    amount_remaining = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True)
    payouts          = OwnerProfitPayoutReadSerializer(many=True, read_only=True)

    class Meta:
        model  = MonthlyProfitOwnerShare
        fields = [
            "id", "share_amount", "amount_paid_out", "amount_reinvested",
            "amount_settled", "amount_remaining", "payment_status", "payouts",
        ]
        read_only_fields = fields

    # Same as MonthlyProfitInvestorShareSerializer — payouts are filtered and
    # ordered by the selector's Prefetch, read straight from its cache.


class InvestorMonthlyShareListItemSerializer(serializers.ModelSerializer):
    period            = serializers.CharField(source="monthly_profit.period", read_only=True)
    amount_settled    = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True)
    amount_remaining  = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True)

    class Meta:
        model  = MonthlyProfitInvestorShare
        fields = [
            "id", "period", "share_percent_snapshot", "share_amount",
            "amount_paid_out", "amount_reinvested", "amount_settled",
            "amount_remaining", "payment_status",
        ]
        read_only_fields = fields


class MonthlyProfitListSerializer(serializers.ModelSerializer):
    class Meta:
        model  = MonthlyProfit
        fields = ["period", "gross_profit", "net_gross_profit", "net_profit", "computed_at"]
        read_only_fields = fields


class MonthlyProfitDetailSerializer(serializers.ModelSerializer):
    investor_shares = MonthlyProfitInvestorShareSerializer(many=True, read_only=True)
    owner_share     = MonthlyProfitOwnerShareSerializer(read_only=True)

    class Meta:
        model  = MonthlyProfit
        fields = [
            "period",
            "gross_revenue", "gross_cogs", "gross_profit",
            "net_revenue", "net_cogs", "net_gross_profit",
            "expenses_paid", "recurring_expenses_paid", "gst_paid", "wht_paid",
            "lost_cash", "found_cash", "lost_inventory", "found_inventory",
            "depreciation", "disposal_gain_loss",
            "net_profit",
            "total_investor_share_percent", "total_investor_share_amount",
            "owner_share_percent", "owner_share_amount",
            "computed_at", "investor_shares", "owner_share",
        ]
        read_only_fields = fields


class InvestorSharePreviewSerializer(serializers.Serializer):
    id            = serializers.IntegerField()
    name          = serializers.CharField()
    share_percent = serializers.DecimalField(max_digits=10, decimal_places=4)
    share_amount  = serializers.DecimalField(max_digits=20, decimal_places=4)


class CurrentMonthProfitSerializer(serializers.Serializer):
    period                    = serializers.CharField()
    is_provisional             = serializers.BooleanField()
    gross_revenue              = serializers.DecimalField(max_digits=20, decimal_places=4)
    gross_cogs                  = serializers.DecimalField(max_digits=20, decimal_places=4)
    gross_profit                = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_revenue                 = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_cogs                    = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_gross_profit            = serializers.DecimalField(max_digits=20, decimal_places=4)
    expenses_paid                = serializers.DecimalField(max_digits=20, decimal_places=4)
    recurring_expenses_paid      = serializers.DecimalField(max_digits=20, decimal_places=4)
    gst_paid                      = serializers.DecimalField(max_digits=20, decimal_places=4)
    wht_paid                      = serializers.DecimalField(max_digits=20, decimal_places=4)
    lost_cash                      = serializers.DecimalField(max_digits=20, decimal_places=4)
    found_cash                     = serializers.DecimalField(max_digits=20, decimal_places=4)
    lost_inventory                 = serializers.DecimalField(max_digits=20, decimal_places=4)
    found_inventory                = serializers.DecimalField(max_digits=20, decimal_places=4)
    depreciation                   = serializers.DecimalField(max_digits=20, decimal_places=4)
    disposal_gain_loss             = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_profit                     = serializers.DecimalField(max_digits=20, decimal_places=4)

    # Live preview only — informational, matches the same % Business Worth
    # uses today. Never stored, no settle actions apply to it.
    investors_preview           = InvestorSharePreviewSerializer(many=True)
    owner_share_percent          = serializers.DecimalField(max_digits=10, decimal_places=4)
    owner_share_amount_preview   = serializers.DecimalField(max_digits=20, decimal_places=4)


class NetProfitTrendItemSerializer(serializers.Serializer):
    month             = serializers.CharField()
    gross_profit      = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_gross_profit  = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_profit        = serializers.DecimalField(max_digits=20, decimal_places=4)


class ProfitFlowStatsSerializer(serializers.Serializer):
    total_gross_profit             = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_net_gross_profit         = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_net_profit               = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_investor_profit_share    = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_owner_profit_share       = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_paid_out_to_investors    = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_reinvested_by_investors  = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_paid_out_to_owner        = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_reinvested_by_owner      = serializers.DecimalField(max_digits=20, decimal_places=4)
    months_finalized_count         = serializers.IntegerField()
