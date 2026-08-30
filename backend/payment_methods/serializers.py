from rest_framework import serializers

from .models import AccountTransfer, PaymentAllocation, PaymentMethod


class PaymentMethodReadSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = PaymentMethod
        fields = [
            "id", "name", "account_number", "balance", "is_protected",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields


class PaymentMethodWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PaymentMethod
        fields = ["name", "account_number"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Method name cannot be blank.")
        return value.strip()


class PaymentAllocationReadSerializer(serializers.ModelSerializer):
    payment_method_name = serializers.CharField(source="payment_method.name", read_only=True)

    class Meta:
        model  = PaymentAllocation
        fields = [
            "id", "payment_method", "payment_method_name", "source_model", "source_id",
            "direction", "amount", "date", "created_at",
        ]
        read_only_fields = fields


class MethodAllocationInputSerializer(serializers.Serializer):
    """
    Shared input shape for "how was this transaction split across methods"
    — used by billing/purchases' payment and advance-payment write
    serializers. Resolves `payment_method` straight to the model instance
    so callers can pass `[(d["payment_method"], d["amount"]) for d in ...]`
    directly into payment_methods.services.record_allocations.
    """
    payment_method = serializers.PrimaryKeyRelatedField(
        queryset=PaymentMethod.objects.filter(is_deleted=False),
    )
    amount = serializers.DecimalField(max_digits=20, decimal_places=4)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


class AccountTransferReadSerializer(serializers.ModelSerializer):
    from_method_name = serializers.CharField(source="from_method.name", read_only=True)
    to_method_name    = serializers.CharField(source="to_method.name", read_only=True)
    created_by        = serializers.StringRelatedField(read_only=True)
    allocations       = serializers.SerializerMethodField()

    class Meta:
        model  = AccountTransfer
        fields = [
            "id", "from_method", "from_method_name", "to_method", "to_method_name",
            "amount", "date", "note", "allocations", "created_by", "created_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        prefetched = self.context.get("account_transfer_allocations")
        if prefetched is not None:
            rows = prefetched.get(obj.id, [])
        else:
            from .selectors import get_allocations_for_source
            rows = get_allocations_for_source(obj)
        return PaymentAllocationReadSerializer(rows, many=True).data


class AccountTransferWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AccountTransfer
        fields = ["from_method", "to_method", "amount", "date", "note"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate(self, attrs):
        if attrs.get("from_method") and attrs.get("to_method") and attrs["from_method"] == attrs["to_method"]:
            raise serializers.ValidationError({"to_method": "Cannot transfer a method to itself."})
        return attrs
