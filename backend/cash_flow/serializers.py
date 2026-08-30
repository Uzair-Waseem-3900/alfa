from rest_framework import serializers

from payment_methods.serializers import MethodAllocationInputSerializer

from .models import CashFlow, Expense, ExpenseCategory


# ---------------------------------------------------------------------------
# ExpenseCategory
# ---------------------------------------------------------------------------

class ExpenseCategoryReadSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = ExpenseCategory
        fields = ["id", "name", "description", "created_by", "created_at"]
        read_only_fields = fields


class ExpenseCategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ExpenseCategory
        fields = ["name", "description"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Category name cannot be blank.")
        return value.strip()


# ---------------------------------------------------------------------------
# Expense
# ---------------------------------------------------------------------------

class ExpenseReadSerializer(serializers.ModelSerializer):
    category    = ExpenseCategoryReadSerializer(read_only=True)
    created_by  = serializers.StringRelatedField(read_only=True)
    updated_by  = serializers.StringRelatedField(read_only=True)
    allocations = serializers.SerializerMethodField()

    class Meta:
        model  = Expense
        fields = [
            "id", "name", "category", "description", "amount", "expense_date", "allocations",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        from payment_methods.serializers import PaymentAllocationReadSerializer

        prefetched = self.context.get("expense_allocations")
        if prefetched is not None:
            rows = prefetched.get(obj.id, [])
        else:
            from payment_methods.selectors import get_allocations_for_source
            rows = get_allocations_for_source(obj)
        return PaymentAllocationReadSerializer(rows, many=True).data


class ExpenseWriteSerializer(serializers.ModelSerializer):
    method_allocations = MethodAllocationInputSerializer(
        many=True, required=False,
        help_text="Required on create, and whenever amount changes on update.",
    )

    class Meta:
        model  = Expense
        fields = ["name", "category", "description", "amount", "expense_date", "method_allocations"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Expense name cannot be blank.")
        return value.strip()


# ---------------------------------------------------------------------------
# Opening/closing cash (cash-in-hand breakdown, filter-only)
# ---------------------------------------------------------------------------

class OpeningClosingCashSerializer(serializers.Serializer):
    opening_cash = serializers.DecimalField(max_digits=20, decimal_places=4)
    closing_cash = serializers.DecimalField(max_digits=20, decimal_places=4)


# ---------------------------------------------------------------------------
# CashFlow stats (dashboard — 17 numbers)
# ---------------------------------------------------------------------------

class CashFlowStatsSerializer(serializers.Serializer):
    """
    Read-only serializer for the 17 dashboard stats.
    Counts come from .count() queries in the selector, not the model.
    """
    # Receivables
    cash_in_hand             = serializers.DecimalField(max_digits=20, decimal_places=4)
    customer_outstanding     = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_invoices_cash      = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_number_of_invoices = serializers.IntegerField()

    # Payables
    total_paid_payables          = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_outstanding_payable    = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_purchases_cash         = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_number_of_purchases    = serializers.IntegerField()

    # Expenses
    total_expenses_amount        = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_number_of_expenses     = serializers.IntegerField()
    total_recurring_expenses_paid = serializers.DecimalField(max_digits=20, decimal_places=4)

    # Lost inventory
    total_lost_inventory_worth     = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_lost_inventory_recovered = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_lost_inventory_worth       = serializers.DecimalField(max_digits=20, decimal_places=4)

    # Returns
    total_purchase_returns_value = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_purchase_returns_cogs  = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_customer_returns_value = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_customer_returns_cogs  = serializers.DecimalField(max_digits=20, decimal_places=4)

    # Profit / margin
    total_invoice_revenue        = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_invoice_cogs           = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_gross_profit           = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_invoice_revenue          = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_invoice_cogs             = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_gross_profit             = serializers.DecimalField(max_digits=20, decimal_places=4)


# ---------------------------------------------------------------------------
# Breakdown serializers — reuse existing app serializers where possible
# ---------------------------------------------------------------------------

class InvoicePaymentBreakdownSerializer(serializers.Serializer):
    """Slim payment record for cash_in_hand breakdown."""
    id              = serializers.IntegerField()
    bill_number     = serializers.CharField(source="invoice.bill_number")
    customer_name   = serializers.CharField(source="invoice.customer.name")
    customer_code   = serializers.CharField(source="invoice.customer.code")
    amount          = serializers.DecimalField(max_digits=18, decimal_places=4)
    method          = serializers.CharField()
    method_display  = serializers.CharField(source="get_method_display")
    payment_date    = serializers.DateField()
    created_by      = serializers.StringRelatedField()
    created_at      = serializers.DateTimeField()


class CustomerOutstandingBreakdownSerializer(serializers.Serializer):
    """Slim invoice record for customer_outstanding breakdown."""
    id                  = serializers.IntegerField()
    bill_number         = serializers.CharField()
    customer_name       = serializers.CharField(source="customer.name")
    customer_code       = serializers.CharField(source="customer.code")
    grand_total         = serializers.DecimalField(max_digits=18, decimal_places=4)
    credit_outstanding  = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_paid          = serializers.DecimalField(max_digits=18, decimal_places=4)
    payment_status      = serializers.CharField()
    confirmed_at        = serializers.DateTimeField()


class SupplierPaymentBreakdownSerializer(serializers.Serializer):
    """Slim supplier payment record for total_paid_payables breakdown."""
    id              = serializers.IntegerField()
    order_number    = serializers.CharField(source="order.order_number")
    supplier_name   = serializers.CharField(source="order.supplier.name")
    supplier_code   = serializers.CharField(source="order.supplier.code")
    amount          = serializers.DecimalField(max_digits=18, decimal_places=4)
    method          = serializers.CharField()
    method_display  = serializers.CharField(source="get_method_display")
    payment_date    = serializers.DateField()
    created_by      = serializers.StringRelatedField()
    created_at      = serializers.DateTimeField()


class SupplierOutstandingBreakdownSerializer(serializers.Serializer):
    """Slim PO record for supplier_payable_outstanding breakdown."""
    id                    = serializers.IntegerField()
    order_number          = serializers.CharField()
    supplier_name         = serializers.CharField(source="supplier.name")
    supplier_code         = serializers.CharField(source="supplier.code")
    net_payable           = serializers.DecimalField(max_digits=18, decimal_places=4)
    payable_outstanding   = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_paid            = serializers.DecimalField(max_digits=18, decimal_places=4)
    payment_status        = serializers.CharField()
    confirmed_at          = serializers.DateTimeField()


class InvoiceBreakdownSerializer(serializers.Serializer):
    """Slim invoice for total_number_of_invoices breakdown."""
    id              = serializers.IntegerField()
    bill_number     = serializers.CharField()
    customer_name   = serializers.CharField(source="customer.name")
    customer_code   = serializers.CharField(source="customer.code")
    grand_total     = serializers.DecimalField(max_digits=18, decimal_places=4)
    payment_status  = serializers.CharField()
    status          = serializers.CharField()
    confirmed_at    = serializers.DateTimeField()
    created_at      = serializers.DateTimeField()


class PurchaseBreakdownSerializer(serializers.Serializer):
    """Slim PO for total_number_of_purchases breakdown."""
    id              = serializers.IntegerField()
    order_number    = serializers.CharField()
    supplier_name   = serializers.CharField(source="supplier.name")
    supplier_code   = serializers.CharField(source="supplier.code")
    net_payable     = serializers.DecimalField(max_digits=18, decimal_places=4)
    payment_status  = serializers.CharField()
    payment_type    = serializers.CharField()
    confirmed_at    = serializers.DateTimeField()
    created_at      = serializers.DateTimeField()


class LostInventoryBreakdownSerializer(serializers.Serializer):
    """Slim lost-inventory item for total_lost_inventory_worth breakdown."""
    id                = serializers.IntegerField()
    reference_number  = serializers.CharField(source="record.reference_number")
    product_name      = serializers.CharField(source="product.name")
    product_code      = serializers.CharField(source="product.code")
    quantity          = serializers.IntegerField()
    reason            = serializers.CharField()
    unit_cost         = serializers.DecimalField(max_digits=14, decimal_places=4)
    total_cost        = serializers.DecimalField(max_digits=18, decimal_places=4)
    note              = serializers.CharField(source="record.note")
    created_by        = serializers.StringRelatedField(source="record.created_by")
    created_at        = serializers.DateTimeField(source="record.created_at")


class PurchaseReturnBreakdownSerializer(serializers.Serializer):
    """Slim purchase return for total_purchase_returns_value/cogs breakdown."""
    id                  = serializers.IntegerField()
    reference_number    = serializers.CharField()
    order_number        = serializers.CharField(source="order.order_number")
    supplier_name       = serializers.CharField(source="order.supplier.name")
    supplier_code       = serializers.CharField(source="order.supplier.code")
    total_return_amount = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_return_gross  = serializers.DecimalField(max_digits=18, decimal_places=4)
    accepted_at         = serializers.DateTimeField()


class CustomerReturnBreakdownSerializer(serializers.Serializer):
    """Slim customer return for total_customer_returns_value/cogs breakdown."""
    id                  = serializers.IntegerField()
    reference_number    = serializers.CharField()
    bill_number         = serializers.CharField(source="invoice.bill_number")
    customer_name       = serializers.CharField(source="invoice.customer.name")
    customer_code       = serializers.CharField(source="invoice.customer.code")
    total_return_amount = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_return_cogs   = serializers.DecimalField(max_digits=18, decimal_places=4)
    accepted_at         = serializers.DateTimeField()


class ProfitBreakdownSerializer(serializers.Serializer):
    """Slim invoice for total_invoice_revenue/cogs/total_gross_profit breakdown."""
    id            = serializers.IntegerField()
    bill_number   = serializers.CharField()
    customer_name = serializers.CharField(source="customer.name")
    customer_code = serializers.CharField(source="customer.code")
    grand_total   = serializers.DecimalField(max_digits=18, decimal_places=4)
    total_cogs    = serializers.DecimalField(max_digits=18, decimal_places=4)
    gross_profit  = serializers.DecimalField(max_digits=18, decimal_places=4)
    confirmed_at  = serializers.DateTimeField()