from rest_framework import serializers

from payment_methods.serializers import MethodAllocationInputSerializer

from .models import TaxPayment, WHTPayment


def _allocations_field(obj, context, context_key):
    """Shared body for every get_allocations method below — prefer the
    batch-prefetched map (list contexts) over a live per-object query,
    which would N+1 across every row on the page."""
    from payment_methods.serializers import PaymentAllocationReadSerializer

    prefetched = context.get(context_key)
    if prefetched is not None:
        rows = prefetched.get(obj.id, [])
    else:
        from payment_methods.selectors import get_allocations_for_source
        rows = get_allocations_for_source(obj)
    return PaymentAllocationReadSerializer(rows, many=True).data


class TaxStatsSerializer(serializers.Serializer):
    """Read-only serializer for the 9 tax-position stats."""
    total_input_tax_paid              = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_output_tax_collected        = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_sales_tax_payable             = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_sales_tax_paid              = serializers.DecimalField(max_digits=20, decimal_places=4)
    sales_tax_outstanding             = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_wht_withheld_from_suppliers = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_wht_withheld_by_customers   = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_wht_paid                    = serializers.DecimalField(max_digits=20, decimal_places=4)
    wht_outstanding                   = serializers.DecimalField(max_digits=20, decimal_places=4)


class TaxPaymentReadSerializer(serializers.ModelSerializer):
    created_by  = serializers.StringRelatedField(read_only=True)
    updated_by  = serializers.StringRelatedField(read_only=True)
    allocations = serializers.SerializerMethodField()

    class Meta:
        model  = TaxPayment
        fields = [
            "id", "amount", "payment_date", "note", "allocations",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        return _allocations_field(obj, self.context, "tax_payment_allocations")


class TaxPaymentWriteSerializer(serializers.ModelSerializer):
    method_allocations = MethodAllocationInputSerializer(many=True)

    class Meta:
        model  = TaxPayment
        fields = ["amount", "payment_date", "note", "method_allocations"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_method_allocations(self, value):
        if not value:
            raise serializers.ValidationError("At least one method must be selected.")
        return value


class WHTPaymentReadSerializer(serializers.ModelSerializer):
    created_by  = serializers.StringRelatedField(read_only=True)
    updated_by  = serializers.StringRelatedField(read_only=True)
    allocations = serializers.SerializerMethodField()

    class Meta:
        model  = WHTPayment
        fields = [
            "id", "amount", "payment_date", "note", "allocations",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        return _allocations_field(obj, self.context, "wht_payment_allocations")


class WHTPaymentWriteSerializer(serializers.ModelSerializer):
    method_allocations = MethodAllocationInputSerializer(many=True)

    class Meta:
        model  = WHTPayment
        fields = ["amount", "payment_date", "note", "method_allocations"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_method_allocations(self, value):
        if not value:
            raise serializers.ValidationError("At least one method must be selected.")
        return value
