from rest_framework import serializers

from assets.models import AssetValuationEntry
from billing.models import Invoice, Payment, Return
from cash_flow.models import Expense
from profits.models import MonthlyProfit
from purchases.models import LostInventoryItem, PurchaseOrder, PurchaseReturn
from recurring_expenses.models import RecurringExpenseAssignment


# ---------------------------------------------------------------------------
# Shared query-param validation — used by both report views (DRY)
# ---------------------------------------------------------------------------

class ReportDateFilterSerializer(serializers.Serializer):
    """
    Validates the date filters accepted by every report endpoint.
    Either a single `date`, or a `date_from`/`date_to` range — not both.
    """
    date      = serializers.DateField(required=False, allow_null=True)
    date_from = serializers.DateField(required=False, allow_null=True)
    date_to   = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        date      = attrs.get("date")
        date_from = attrs.get("date_from")
        date_to   = attrs.get("date_to")

        if date and (date_from or date_to):
            raise serializers.ValidationError(
                "Use either `date` or `date_from`/`date_to`, not both."
            )
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError(
                "`date_from` cannot be after `date_to`."
            )
        return attrs


# ---------------------------------------------------------------------------
# Invoices report — lightweight list item (not the full InvoiceReadSerializer)
# ---------------------------------------------------------------------------

class InvoiceReportItemSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    confirmed_at  = serializers.DateTimeField(format="%d %b %Y", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "bill_number", "customer_name",
            "grand_total", "payment_status", "confirmed_at", "payment_due_date",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Cash collected report — lightweight list item
# ---------------------------------------------------------------------------

class PaymentReportItemSerializer(serializers.ModelSerializer):
    invoice_bill_number = serializers.CharField(source="invoice.bill_number", read_only=True)
    customer_name       = serializers.CharField(source="invoice.customer.name", read_only=True)
    method_display       = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id", "reference_number", "invoice_bill_number", "customer_name",
            "amount", "method", "method_display", "payment_date",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Expenses report — lightweight list item
# ---------------------------------------------------------------------------

class ExpenseReportItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Expense
        fields = ["id", "name", "category_name", "amount", "expense_date"]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Lost inventory report — lightweight list item
# ---------------------------------------------------------------------------

class LostInventoryReportItemSerializer(serializers.ModelSerializer):
    reference_number  = serializers.CharField(source="record.reference_number", read_only=True)
    product_name      = serializers.CharField(source="product.name", read_only=True)
    product_code      = serializers.CharField(source="product.code", read_only=True)
    created_at        = serializers.DateTimeField(source="record.created_at", read_only=True)
    recovered_amount  = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    net_amount        = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)

    class Meta:
        model = LostInventoryItem
        fields = [
            "id", "reference_number", "product_name", "product_code",
            "quantity", "found_quantity", "reason",
            "unit_cost", "total_cost", "recovered_amount", "net_amount",
            "created_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Purchase returns report — lightweight list item
# ---------------------------------------------------------------------------

class PurchaseReturnReportItemSerializer(serializers.ModelSerializer):
    order_number  = serializers.CharField(source="order.order_number", read_only=True)
    supplier_name = serializers.CharField(source="order.supplier.name", read_only=True)
    accepted_at   = serializers.DateTimeField(format="%d %b %Y", read_only=True)

    class Meta:
        model = PurchaseReturn
        fields = [
            "id", "reference_number", "order_number", "supplier_name",
            "total_return_gross", "total_return_gst", "total_return_wht",
            "total_return_amount", "accepted_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Customer returns report — lightweight list item
# ---------------------------------------------------------------------------

class CustomerReturnReportItemSerializer(serializers.ModelSerializer):
    bill_number   = serializers.CharField(source="invoice.bill_number", read_only=True)
    customer_name = serializers.CharField(source="invoice.customer.name", read_only=True)
    accepted_at   = serializers.DateTimeField(format="%d %b %Y", read_only=True)

    class Meta:
        model = Return
        fields = [
            "id", "reference_number", "bill_number", "customer_name",
            "total_return_amount", "total_return_cogs", "accepted_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Profit / margin report — lightweight list item
# ---------------------------------------------------------------------------

class ProfitMarginReportItemSerializer(serializers.ModelSerializer):
    customer_name  = serializers.CharField(source="customer.name", read_only=True)
    margin_percent = serializers.SerializerMethodField()
    confirmed_at   = serializers.DateTimeField(format="%d %b %Y", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "bill_number", "customer_name",
            "grand_total", "total_cogs", "gross_profit",
            "margin_percent", "confirmed_at",
        ]
        read_only_fields = fields

    def get_margin_percent(self, obj):
        if not obj.grand_total:
            return 0
        return round(obj.gross_profit / obj.grand_total * 100, 4)


# ---------------------------------------------------------------------------
# Inventory valuation report — plain serializer, rows are dicts not models
# ---------------------------------------------------------------------------

class InventoryValuationReportItemSerializer(serializers.Serializer):
    product_id       = serializers.IntegerField()
    product_name     = serializers.CharField()
    product_code     = serializers.CharField()
    category_name    = serializers.CharField()
    quantity_on_hand = serializers.IntegerField()
    avg_unit_cost    = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_value      = serializers.DecimalField(max_digits=20, decimal_places=4)


# ---------------------------------------------------------------------------
# Sales Tax report — Input Tax (purchases) side, lightweight list item
# ---------------------------------------------------------------------------

class InputTaxReportItemSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    supplier_code = serializers.CharField(source="supplier.code", read_only=True)
    confirmed_at  = serializers.DateTimeField(format="%d %b %Y", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id", "order_number", "supplier_name", "supplier_code",
            "gst_total", "wht_total", "net_payable", "confirmed_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Sales Tax report — Output Tax (invoices) side, lightweight list item
# ---------------------------------------------------------------------------

class OutputTaxReportItemSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_code = serializers.CharField(source="customer.code", read_only=True)
    confirmed_at  = serializers.DateTimeField(format="%d %b %Y", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "bill_number", "customer_name", "customer_code",
            "gst_total", "wht_total", "grand_total", "confirmed_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Recurring expenses report — lightweight list item
# ---------------------------------------------------------------------------

class RecurringExpenseReportItemSerializer(serializers.ModelSerializer):
    assigned_at = serializers.DateTimeField(format="%d %b %Y", read_only=True)

    class Meta:
        model = RecurringExpenseAssignment
        fields = [
            "id", "name_snapshot", "category_name_snapshot", "period",
            "amount", "amount_paid", "payment_status", "assigned_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Net profit report — lightweight list item (one row per finalized month)
# ---------------------------------------------------------------------------

class NetProfitReportItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MonthlyProfit
        fields = [
            "period", "gross_profit", "net_gross_profit",
            "expenses_paid", "recurring_expenses_paid", "gst_paid", "wht_paid",
            "lost_cash", "found_cash", "lost_inventory", "found_inventory",
            "depreciation", "disposal_gain_loss",
            "net_profit", "total_investor_share_amount", "owner_share_amount",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Asset depreciation report — lightweight list item
# ---------------------------------------------------------------------------

class AssetDepreciationReportItemSerializer(serializers.ModelSerializer):
    asset_name    = serializers.CharField(source="asset.name", read_only=True)
    category_name = serializers.CharField(source="asset.category.name", read_only=True)

    class Meta:
        model = AssetValuationEntry
        fields = [
            "id", "asset_name", "category_name", "period",
            "rate_applied", "worth_before", "worth_after", "amount", "created_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Stock movement report — rows are plain dicts (grouped across 4 source
# tables), not a single model's instances, so this is a plain Serializer.
# ---------------------------------------------------------------------------

class StockMovementReportItemSerializer(serializers.Serializer):
    product_id              = serializers.IntegerField()
    product_name            = serializers.CharField()
    product_code            = serializers.CharField()
    total_purchased         = serializers.IntegerField()
    total_purchase_returned = serializers.IntegerField()
    total_sold               = serializers.IntegerField()
    total_sale_returned      = serializers.IntegerField()
    total_lost                = serializers.IntegerField()
    total_found               = serializers.IntegerField()
