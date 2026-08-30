from rest_framework import serializers

from payment_methods.serializers import MethodAllocationInputSerializer

from .models import (
    RecurringExpense, RecurringExpenseAssignment, RecurringExpenseAssignmentPayment,
    RecurringExpenseCategory,
)


# ---------------------------------------------------------------------------
# RecurringExpenseCategory
# ---------------------------------------------------------------------------

class RecurringExpenseCategoryReadSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = RecurringExpenseCategory
        fields = ["id", "name", "description", "created_by", "created_at"]
        read_only_fields = fields


class RecurringExpenseCategoryWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RecurringExpenseCategory
        fields = ["name", "description"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Category name cannot be blank.")
        return value.strip()


# ---------------------------------------------------------------------------
# RecurringExpense (template)
# ---------------------------------------------------------------------------

class RecurringExpenseReadSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    created_by    = serializers.StringRelatedField(read_only=True)
    updated_by    = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = RecurringExpense
        fields = [
            "id", "name", "category", "category_name", "amount", "start_date",
            "is_active", "note", "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields


class RecurringExpenseWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model  = RecurringExpense
        fields = ["name", "category", "amount", "start_date", "is_active", "note"]
        extra_kwargs = {
            "category":   {"required": False},
            "amount":     {"required": False},
            "start_date": {"required": False},
            "is_active":  {"required": False},
        }

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be blank.")
        return value.strip()

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


# ---------------------------------------------------------------------------
# RecurringExpenseAssignment
# ---------------------------------------------------------------------------

class RecurringExpenseAssignmentReadSerializer(serializers.ModelSerializer):
    assigned_by      = serializers.StringRelatedField(read_only=True)
    amount_pending    = serializers.SerializerMethodField()

    class Meta:
        model  = RecurringExpenseAssignment
        fields = [
            "id", "recurring_expense", "name_snapshot", "period",
            "category", "category_name_snapshot", "amount", "amount_paid",
            "amount_pending", "payment_status", "note", "assigned_by", "assigned_at",
        ]
        read_only_fields = fields

    def get_amount_pending(self, obj):
        return obj.amount - obj.amount_paid


class RecurringExpenseAssignmentCreateSerializer(serializers.Serializer):
    recurring_expense = serializers.PrimaryKeyRelatedField(queryset=RecurringExpense.objects.filter(is_deleted=False))
    period            = serializers.CharField(max_length=7)


class RecurringExpenseAssignmentBulkCreateSerializer(serializers.Serializer):
    period      = serializers.CharField(max_length=7)
    category_id = serializers.IntegerField(required=False, allow_null=True)


# ---------------------------------------------------------------------------
# RecurringExpenseAssignmentPayment
# ---------------------------------------------------------------------------

class RecurringExpenseAssignmentPaymentReadSerializer(serializers.ModelSerializer):
    created_by  = serializers.StringRelatedField(read_only=True)
    updated_by  = serializers.StringRelatedField(read_only=True)
    allocations = serializers.SerializerMethodField()

    class Meta:
        model  = RecurringExpenseAssignmentPayment
        fields = [
            "id", "assignment", "amount", "payment_date", "note", "allocations",
            "created_by", "updated_by", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_allocations(self, obj):
        from payment_methods.serializers import PaymentAllocationReadSerializer

        prefetched = self.context.get("recurring_expense_payment_allocations")
        if prefetched is not None:
            rows = prefetched.get(obj.id, [])
        else:
            from payment_methods.selectors import get_allocations_for_source
            rows = get_allocations_for_source(obj)
        return PaymentAllocationReadSerializer(rows, many=True).data


class RecurringExpenseAssignmentPaymentWriteSerializer(serializers.ModelSerializer):
    method_allocations = MethodAllocationInputSerializer(many=True)

    class Meta:
        model  = RecurringExpenseAssignmentPayment
        fields = ["assignment", "amount", "payment_date", "note", "method_allocations"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_method_allocations(self, value):
        if not value:
            raise serializers.ValidationError("At least one method must be selected.")
        return value


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class RecurringExpenseFlowStatsSerializer(serializers.Serializer):
    total_assigned_amount           = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_paid_amount               = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_pending_amount            = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_assignments_count         = serializers.IntegerField()
    total_active_templates          = serializers.IntegerField()
    total_active_monthly_obligation = serializers.DecimalField(max_digits=20, decimal_places=4)


class RecurringExpenseMonthlyStatsSerializer(serializers.Serializer):
    period          = serializers.CharField()
    total_assigned  = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_paid      = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_pending   = serializers.DecimalField(max_digits=20, decimal_places=4)
    is_fully_paid   = serializers.BooleanField()
