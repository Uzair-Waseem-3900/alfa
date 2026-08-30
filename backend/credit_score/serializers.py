from rest_framework import serializers

from .models import CreditScoreHistory, CustomerCreditScore


class CustomerCreditScoreSerializer(serializers.ModelSerializer):
    customer_id   = serializers.IntegerField(source="customer.id", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_code = serializers.CharField(source="customer.code", read_only=True)
    tier_display  = serializers.CharField(source="get_tier_display", read_only=True)

    class Meta:
        model = CustomerCreditScore
        fields = [
            "customer_id", "customer_name", "customer_code",
            "score", "tier", "tier_display", "factor_breakdown", "last_calculated_at",
        ]
        read_only_fields = fields


class CreditScoreHistorySerializer(serializers.ModelSerializer):
    delta = serializers.SerializerMethodField()

    class Meta:
        model = CreditScoreHistory
        fields = [
            "id", "score_before", "score_after", "delta",
            "tier_before", "tier_after", "trigger", "reference",
            "factor_breakdown", "created_at",
        ]
        read_only_fields = fields

    def get_delta(self, obj):
        if obj.score_before is None:
            return None
        return obj.score_after - obj.score_before
