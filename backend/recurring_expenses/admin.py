from django.contrib import admin

from .models import (
    RecurringExpense, RecurringExpenseAssignment, RecurringExpenseAssignmentPayment,
    RecurringExpenseCategory, RecurringExpenseFlow, RecurringExpenseMonthlyStats,
)


class AuditAdminMixin:
    readonly_fields = ("created_by", "updated_by", "deleted_by", "created_at", "updated_at", "deleted_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(RecurringExpenseCategory)
class RecurringExpenseCategoryAdmin(admin.ModelAdmin):
    list_display  = ["name", "is_deleted", "created_by", "created_at"]
    list_filter   = ["is_deleted"]
    search_fields = ["name"]
    readonly_fields = ("created_by", "deleted_by", "created_at", "deleted_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(RecurringExpense)
class RecurringExpenseAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display  = ["name", "category", "amount", "is_active", "start_date", "is_deleted"]
    list_filter   = ["is_active", "is_deleted", "category"]
    search_fields = ["name"]


@admin.register(RecurringExpenseAssignment)
class RecurringExpenseAssignmentAdmin(admin.ModelAdmin):
    list_display  = ["name_snapshot", "period", "category_name_snapshot", "amount", "amount_paid", "payment_status", "is_deleted"]
    list_filter   = ["payment_status", "period", "is_deleted"]
    search_fields = ["name_snapshot"]
    readonly_fields = [f.name for f in RecurringExpenseAssignment._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RecurringExpenseAssignmentPayment)
class RecurringExpenseAssignmentPaymentAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display  = ["assignment", "amount", "payment_date", "is_deleted"]
    list_filter   = ["is_deleted"]
    search_fields = ["assignment__name_snapshot"]

    def has_add_permission(self, request):
        return False


@admin.register(RecurringExpenseFlow)
class RecurringExpenseFlowAdmin(admin.ModelAdmin):
    list_display = [
        "total_assigned_amount", "total_paid_amount", "total_pending_amount",
        "total_active_templates", "total_active_monthly_obligation", "last_updated_at",
    ]
    readonly_fields = [f.name for f in RecurringExpenseFlow._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RecurringExpenseMonthlyStats)
class RecurringExpenseMonthlyStatsAdmin(admin.ModelAdmin):
    list_display  = ["period", "total_assigned", "total_paid", "total_pending", "is_fully_paid"]
    list_filter   = ["is_fully_paid"]
    readonly_fields = [f.name for f in RecurringExpenseMonthlyStats._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
