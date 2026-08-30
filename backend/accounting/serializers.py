from rest_framework import serializers


# ---------------------------------------------------------------------------
# A/R Aging
# ---------------------------------------------------------------------------

class ARAgingRowSerializer(serializers.Serializer):
    invoice_id     = serializers.IntegerField()
    bill_number    = serializers.CharField()
    customer_id    = serializers.IntegerField()
    customer_name  = serializers.CharField()
    customer_code  = serializers.CharField()
    due_date       = serializers.DateField()
    days_overdue   = serializers.IntegerField()
    bucket         = serializers.CharField()
    outstanding    = serializers.DecimalField(max_digits=18, decimal_places=4)


# ---------------------------------------------------------------------------
# A/P Aging
# ---------------------------------------------------------------------------

class APAgingRowSerializer(serializers.Serializer):
    order_id        = serializers.IntegerField()
    order_number    = serializers.CharField()
    supplier_id     = serializers.IntegerField()
    supplier_name   = serializers.CharField()
    supplier_code   = serializers.CharField()
    confirmed_date  = serializers.DateField()
    days_overdue    = serializers.IntegerField()
    bucket          = serializers.CharField()
    outstanding     = serializers.DecimalField(max_digits=18, decimal_places=4)


# ---------------------------------------------------------------------------
# Fixed Asset Register
# ---------------------------------------------------------------------------

class FixedAssetRegisterRowSerializer(serializers.Serializer):
    asset_id                   = serializers.IntegerField()
    name                       = serializers.CharField()
    category                   = serializers.CharField()
    valuation_method           = serializers.CharField()
    acquisition_date           = serializers.DateField()
    cost                       = serializers.DecimalField(max_digits=18, decimal_places=4)
    accumulated_depreciation   = serializers.DecimalField(max_digits=18, decimal_places=4)
    net_book_value             = serializers.DecimalField(max_digits=18, decimal_places=4)
    is_disposed                = serializers.BooleanField()
    disposal_date              = serializers.DateField(allow_null=True)
    disposal_type              = serializers.CharField(allow_null=True)
    gain_loss_on_disposal      = serializers.DecimalField(max_digits=18, decimal_places=4, allow_null=True)


# ---------------------------------------------------------------------------
# Cash Flow Statement
# ---------------------------------------------------------------------------

class CashFlowLineSerializer(serializers.Serializer):
    label   = serializers.CharField()
    amount  = serializers.DecimalField(max_digits=20, decimal_places=4)


class CashFlowActivitySerializer(serializers.Serializer):
    lines = CashFlowLineSerializer(many=True)
    net   = serializers.DecimalField(max_digits=20, decimal_places=4)


class CashFlowStatementSerializer(serializers.Serializer):
    date_from           = serializers.CharField()
    date_to             = serializers.CharField()
    operating            = CashFlowActivitySerializer()
    investing             = CashFlowActivitySerializer()
    financing              = CashFlowActivitySerializer()
    net_change_in_cash      = serializers.DecimalField(max_digits=20, decimal_places=4)
    opening_cash             = serializers.DecimalField(max_digits=20, decimal_places=4, allow_null=True)
    closing_cash              = serializers.DecimalField(max_digits=20, decimal_places=4, allow_null=True)


# ---------------------------------------------------------------------------
# Income Statement
# ---------------------------------------------------------------------------

class ExpenseBreakdownLineSerializer(serializers.Serializer):
    category = serializers.CharField(allow_null=True)
    amount   = serializers.DecimalField(max_digits=18, decimal_places=4)


class IncomeStatementSerializer(serializers.Serializer):
    period                     = serializers.CharField()
    is_provisional              = serializers.BooleanField()
    gross_revenue                = serializers.DecimalField(max_digits=20, decimal_places=4)
    gross_cogs                    = serializers.DecimalField(max_digits=20, decimal_places=4)
    gross_profit                   = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_revenue                     = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_cogs                         = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_gross_profit                  = serializers.DecimalField(max_digits=20, decimal_places=4)
    expenses_paid                      = serializers.DecimalField(max_digits=20, decimal_places=4)
    recurring_expenses_paid             = serializers.DecimalField(max_digits=20, decimal_places=4)
    gst_paid                             = serializers.DecimalField(max_digits=20, decimal_places=4)
    wht_paid                              = serializers.DecimalField(max_digits=20, decimal_places=4)
    lost_cash                              = serializers.DecimalField(max_digits=20, decimal_places=4)
    found_cash                              = serializers.DecimalField(max_digits=20, decimal_places=4)
    lost_inventory                           = serializers.DecimalField(max_digits=20, decimal_places=4)
    found_inventory                           = serializers.DecimalField(max_digits=20, decimal_places=4)
    depreciation                               = serializers.DecimalField(max_digits=20, decimal_places=4)
    disposal_gain_loss                          = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_profit                                   = serializers.DecimalField(max_digits=20, decimal_places=4)
    expense_breakdown                             = ExpenseBreakdownLineSerializer(many=True)


# ---------------------------------------------------------------------------
# Balance Sheet
# ---------------------------------------------------------------------------

class BalanceSheetAssetsSerializer(serializers.Serializer):
    cash_in_hand         = serializers.DecimalField(max_digits=20, decimal_places=4)
    accounts_receivable   = serializers.DecimalField(max_digits=20, decimal_places=4)
    inventory_value         = serializers.DecimalField(max_digits=20, decimal_places=4)
    fixed_assets_nbv          = serializers.DecimalField(max_digits=20, decimal_places=4)
    total                       = serializers.DecimalField(max_digits=20, decimal_places=4)


class BalanceSheetLiabilitiesSerializer(serializers.Serializer):
    accounts_payable  = serializers.DecimalField(max_digits=20, decimal_places=4)
    gst_payable         = serializers.DecimalField(max_digits=20, decimal_places=4)
    wht_payable           = serializers.DecimalField(max_digits=20, decimal_places=4)
    total                   = serializers.DecimalField(max_digits=20, decimal_places=4)


class BalanceSheetEquitySerializer(serializers.Serializer):
    owner_capital               = serializers.DecimalField(max_digits=20, decimal_places=4)
    investor_capital             = serializers.DecimalField(max_digits=20, decimal_places=4)
    opening_balance_equity        = serializers.DecimalField(max_digits=20, decimal_places=4)
    pre_owned_asset_equity          = serializers.DecimalField(max_digits=20, decimal_places=4)
    asset_revaluation_surplus        = serializers.DecimalField(max_digits=20, decimal_places=4)
    retained_earnings                  = serializers.DecimalField(max_digits=20, decimal_places=4)
    total                                = serializers.DecimalField(max_digits=20, decimal_places=4)


class BalanceSheetFreshnessSerializer(serializers.Serializer):
    """How late a frozen snapshot was taken — see
    accounting.selectors._snapshot_freshness for why this has to be shown
    rather than corrected. All-null with is_snapshot=False for the live
    "as of today" sheet, which has no lag by definition."""
    is_snapshot        = serializers.BooleanField()
    snapshot_taken_on   = serializers.DateField(allow_null=True)
    lag_days             = serializers.IntegerField(allow_null=True)
    is_stale              = serializers.BooleanField()


class BalanceSheetSerializer(serializers.Serializer):
    assets         = BalanceSheetAssetsSerializer()
    liabilities     = BalanceSheetLiabilitiesSerializer()
    equity           = BalanceSheetEquitySerializer()
    balance_check      = serializers.DecimalField(max_digits=20, decimal_places=4)
    is_balanced          = serializers.BooleanField()
    freshness              = BalanceSheetFreshnessSerializer()
