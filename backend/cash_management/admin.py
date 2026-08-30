from django.contrib import admin

from .models import (
    CashAdjustment, CashManagementFlow, Investor, InvestorTransaction,
    InvestorValuationEntry, OwnerTransaction,
)


@admin.register(CashManagementFlow)
class CashManagementFlowAdmin(admin.ModelAdmin):
    list_display = [
        "total_cash_lost", "total_cash_recovered", "net_cash_lost",
        "total_investor_capital", "total_investor_withdrawn", "net_investor_capital", "total_investor_net_worth",
        "total_owner_contributions", "total_owner_drawings",
        "total_owner_contributions_count", "total_owner_withdrawals_count", "net_owner_capital",
        "last_updated_at",
    ]
    readonly_fields = [f.name for f in CashManagementFlow._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class AuditAdminMixin:
    readonly_fields = ("created_by", "updated_by", "deleted_by", "created_at", "updated_at", "deleted_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(CashAdjustment)
class CashAdjustmentAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display  = ["adjustment_type", "amount", "adjustment_date", "is_deleted", "created_by"]
    list_filter   = ["adjustment_type", "is_deleted"]
    search_fields = ["reason"]


@admin.register(Investor)
class InvestorAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display  = ["name", "total_invested", "total_withdrawn", "net_stake", "growth_rate", "current_worth", "is_deleted"]
    list_filter   = ["is_deleted"]
    search_fields = ["name", "email", "contact_number"]
    readonly_fields = AuditAdminMixin.readonly_fields + ("total_invested", "total_withdrawn", "net_stake", "current_worth")


@admin.register(InvestorTransaction)
class InvestorTransactionAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display  = ["investor", "transaction_type", "amount", "worth_delta", "transaction_date", "is_deleted"]
    list_filter   = ["transaction_type", "is_deleted"]
    search_fields = ["investor__name", "note"]
    readonly_fields = AuditAdminMixin.readonly_fields + ("worth_delta",)


@admin.register(InvestorValuationEntry)
class InvestorValuationEntryAdmin(admin.ModelAdmin):
    list_display  = ["investor", "period", "rate_applied", "amount", "worth_after"]
    search_fields = ["investor__name"]
    readonly_fields = [f.name for f in InvestorValuationEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OwnerTransaction)
class OwnerTransactionAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display  = ["transaction_type", "amount", "transaction_date", "is_deleted", "created_by"]
    list_filter   = ["transaction_type", "is_deleted"]
    search_fields = ["note"]
