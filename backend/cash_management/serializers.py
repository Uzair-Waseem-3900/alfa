from rest_framework import serializers

from payment_methods.serializers import MethodAllocationInputSerializer

from .models import (
    CashAdjustment, Investor, InvestorTransaction, InvestorValuationEntry,
    OwnerTransaction,
)


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


class CashManagementStatsSerializer(serializers.Serializer):
    """Read-only serializer for the 12 cash-management stats."""
    total_cash_lost                 = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_cash_recovered            = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_cash_lost                   = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_investor_capital          = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_investor_withdrawn        = serializers.DecimalField(max_digits=20, decimal_places=4)
    net_investor_capital            = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_investor_net_worth        = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_owner_contributions       = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_owner_drawings            = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_owner_contributions_count = serializers.IntegerField()
    total_owner_withdrawals_count   = serializers.IntegerField()
    net_owner_capital               = serializers.DecimalField(max_digits=20, decimal_places=4)


# ---------------------------------------------------------------------------
# CashAdjustment
# ---------------------------------------------------------------------------

class CashAdjustmentReadSerializer(serializers.ModelSerializer):
    created_by  = serializers.StringRelatedField(read_only=True)
    updated_by  = serializers.StringRelatedField(read_only=True)
    allocations = serializers.SerializerMethodField()

    class Meta:
        model  = CashAdjustment
        fields = [
            "id", "amount", "adjustment_type", "adjustment_date", "reason", "allocations",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        return _allocations_field(obj, self.context, "cash_adjustment_allocations")


class CashAdjustmentWriteSerializer(serializers.ModelSerializer):
    method_allocations = MethodAllocationInputSerializer(many=True)

    class Meta:
        model  = CashAdjustment
        fields = ["amount", "adjustment_type", "adjustment_date", "reason", "method_allocations"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_method_allocations(self, value):
        if not value:
            raise serializers.ValidationError("At least one method must be selected.")
        return value


# ---------------------------------------------------------------------------
# Investor
# ---------------------------------------------------------------------------

class InvestorReadSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)
    updated_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = Investor
        fields = [
            "id", "name", "contact_number", "email", "note",
            "total_invested", "total_withdrawn", "net_stake",
            "growth_rate", "current_worth",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields


class InvestorWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Investor
        fields = ["name", "contact_number", "email", "note", "growth_rate"]
        extra_kwargs = {"growth_rate": {"required": False}}

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Investor name cannot be blank.")
        return value.strip()

    def validate_growth_rate(self, value):
        if value < 0:
            raise serializers.ValidationError("Growth rate cannot be negative.")
        return value


# ---------------------------------------------------------------------------
# InvestorValuationEntry
# ---------------------------------------------------------------------------

class InvestorValuationEntryReadSerializer(serializers.ModelSerializer):
    investor_name = serializers.CharField(source="investor.name", read_only=True)
    created_by    = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = InvestorValuationEntry
        fields = [
            "id", "investor", "investor_name", "period", "rate_applied",
            "worth_before", "worth_after", "amount", "note",
            "created_by", "created_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# InvestorTransaction
# ---------------------------------------------------------------------------

class InvestorTransactionReadSerializer(serializers.ModelSerializer):
    investor_name = serializers.CharField(source="investor.name", read_only=True)
    created_by    = serializers.StringRelatedField(read_only=True)
    updated_by    = serializers.StringRelatedField(read_only=True)
    allocations   = serializers.SerializerMethodField()

    class Meta:
        model  = InvestorTransaction
        fields = [
            "id", "investor", "investor_name", "transaction_type", "amount",
            "worth_delta", "transaction_date", "note", "is_data_entry", "allocations",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        return _allocations_field(obj, self.context, "investor_transaction_allocations")


class InvestorTransactionWriteSerializer(serializers.ModelSerializer):
    investor = serializers.PrimaryKeyRelatedField(queryset=Investor.objects.filter(is_deleted=False))
    method_allocations = MethodAllocationInputSerializer(many=True)

    class Meta:
        model  = InvestorTransaction
        fields = ["investor", "transaction_type", "amount", "transaction_date", "note", "method_allocations"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_method_allocations(self, value):
        if not value:
            raise serializers.ValidationError("At least one method must be selected.")
        return value


# ---------------------------------------------------------------------------
# OwnerTransaction
# ---------------------------------------------------------------------------

class OwnerTransactionReadSerializer(serializers.ModelSerializer):
    created_by  = serializers.StringRelatedField(read_only=True)
    updated_by  = serializers.StringRelatedField(read_only=True)
    allocations = serializers.SerializerMethodField()

    class Meta:
        model  = OwnerTransaction
        fields = [
            "id", "transaction_type", "amount", "transaction_date", "note", "allocations",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        return _allocations_field(obj, self.context, "owner_transaction_allocations")


class OwnerTransactionWriteSerializer(serializers.ModelSerializer):
    method_allocations = MethodAllocationInputSerializer(many=True)

    class Meta:
        model  = OwnerTransaction
        fields = ["transaction_type", "amount", "transaction_date", "note", "method_allocations"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_method_allocations(self, value):
        if not value:
            raise serializers.ValidationError("At least one method must be selected.")
        return value
