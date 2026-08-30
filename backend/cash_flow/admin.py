from django.contrib import admin

from .models import CashFlow, Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display  = ["name", "created_by", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["created_by", "created_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display  = ["name", "category", "amount", "expense_date", "is_deleted", "created_by", "updated_by"]
    list_filter   = ["category", "is_deleted", "expense_date"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_by", "updated_by", "deleted_by", "created_at", "updated_at", "deleted_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CashFlow)
class CashFlowAdmin(admin.ModelAdmin):
    list_display = [
        "cash_in_hand", "customer_outstanding",
        "total_paid_payables", "supplier_payable_outstanding",
        "total_expenses_amount", "last_updated_at", "last_updated_by",
    ]
    readonly_fields = [
        "cash_in_hand", "customer_outstanding",
        "total_paid_payables", "supplier_payable_outstanding",
        "total_expenses_amount", "last_updated_at", "last_updated_by",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False