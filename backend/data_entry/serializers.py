from rest_framework import serializers

from .models import (
    CustomerOpeningBalance, OpeningCashEntry, SupplierOpeningBalance,
)


# ---------------------------------------------------------------------------
# Feature 1 — Supplier Opening Balance
# ---------------------------------------------------------------------------

class SupplierOpeningBalanceWriteSerializer(serializers.Serializer):
    supplier_id = serializers.IntegerField()
    amount      = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)
    note        = serializers.CharField(required=False, allow_blank=True, default="")


class SupplierOpeningBalanceReadSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    supplier_code = serializers.CharField(source="supplier.code", read_only=True)
    order_number  = serializers.CharField(source="purchase_order.order_number", read_only=True)
    created_by    = serializers.CharField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model  = SupplierOpeningBalance
        fields = [
            "id", "supplier", "supplier_name", "supplier_code",
            "amount", "note", "purchase_order", "order_number",
            "created_by", "created_at",
        ]


# ---------------------------------------------------------------------------
# Feature 2 — Customer Opening Balance
# ---------------------------------------------------------------------------

class CustomerOpeningBalanceWriteSerializer(serializers.Serializer):
    customer_id = serializers.IntegerField()
    amount      = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)
    note        = serializers.CharField(required=False, allow_blank=True, default="")


class CustomerOpeningBalanceReadSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_code = serializers.CharField(source="customer.code", read_only=True)
    bill_number   = serializers.CharField(source="invoice.bill_number", read_only=True)
    created_by    = serializers.CharField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model  = CustomerOpeningBalance
        fields = [
            "id", "customer", "customer_name", "customer_code",
            "amount", "note", "invoice", "bill_number",
            "created_by", "created_at",
        ]


# ---------------------------------------------------------------------------
# Feature 3 — Opening Cash
# ---------------------------------------------------------------------------

class OpeningCashWriteSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)


class OpeningCashReadSerializer(serializers.ModelSerializer):
    added_by = serializers.CharField(source="added_by.email", read_only=True, default=None)

    class Meta:
        model  = OpeningCashEntry
        fields = ["id", "amount", "note", "added_by", "added_at"]


# ---------------------------------------------------------------------------
# Feature 4 — Opening Stock
# ---------------------------------------------------------------------------

class OpeningStockItemSerializer(serializers.Serializer):
    product_id  = serializers.IntegerField()
    shelf_id    = serializers.IntegerField()
    quantity    = serializers.IntegerField(min_value=1)
    unit_price  = serializers.DecimalField(max_digits=14, decimal_places=4, min_value=0)
    gst         = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    wht         = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, default=0)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class OpeningStockWriteSerializer(serializers.Serializer):
    items = OpeningStockItemSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value


class _OpeningStockItemReadSerializer(serializers.Serializer):
    product      = serializers.IntegerField(source="product_id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    quantity     = serializers.IntegerField(read_only=True)
    unit_price   = serializers.DecimalField(max_digits=14, decimal_places=4, read_only=True)
    gst          = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    wht          = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    total_price  = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)


class OpeningStockOrderReadSerializer(serializers.Serializer):
    id           = serializers.IntegerField(read_only=True)
    order_number = serializers.CharField(read_only=True)
    net_payable  = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    created_at   = serializers.DateTimeField(read_only=True)
    items        = _OpeningStockItemReadSerializer(many=True, read_only=True)


# ---------------------------------------------------------------------------
# Feature 5 — Opening Investor Investment
# ---------------------------------------------------------------------------

class OpeningInvestorInvestmentWriteSerializer(serializers.Serializer):
    investor_id = serializers.IntegerField()
    amount      = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)
    note        = serializers.CharField(required=False, allow_blank=True, default="")


class OpeningInvestorInvestmentReadSerializer(serializers.Serializer):
    id                = serializers.IntegerField(read_only=True)
    investor          = serializers.IntegerField(source="investor_id", read_only=True)
    investor_name     = serializers.CharField(source="investor.name", read_only=True)
    amount            = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    note              = serializers.CharField(read_only=True)
    transaction_date  = serializers.DateField(read_only=True)
    created_by        = serializers.CharField(source="created_by.email", read_only=True, default=None)
    created_at        = serializers.DateTimeField(read_only=True)
