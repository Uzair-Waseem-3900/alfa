from django.contrib import admin

from .models import InvestorProfitPayout, MonthlyProfit, MonthlyProfitInvestorShare, ProfitFlow


class MonthlyProfitInvestorShareInline(admin.TabularInline):
    model = MonthlyProfitInvestorShare
    extra = 0
    readonly_fields = [f.name for f in MonthlyProfitInvestorShare._meta.fields]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MonthlyProfit)
class MonthlyProfitAdmin(admin.ModelAdmin):
    list_display  = ["period", "gross_profit", "net_gross_profit", "net_profit", "computed_at"]
    readonly_fields = [f.name for f in MonthlyProfit._meta.fields]
    inlines = [MonthlyProfitInvestorShareInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MonthlyProfitInvestorShare)
class MonthlyProfitInvestorShareAdmin(admin.ModelAdmin):
    list_display  = ["monthly_profit", "investor_name_snapshot", "share_percent_snapshot", "share_amount", "payment_status"]
    list_filter   = ["payment_status"]
    search_fields = ["investor_name_snapshot"]
    readonly_fields = [f.name for f in MonthlyProfitInvestorShare._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InvestorProfitPayout)
class InvestorProfitPayoutAdmin(admin.ModelAdmin):
    list_display  = ["share", "action_type", "amount", "payout_date", "is_deleted", "created_by"]
    list_filter   = ["action_type", "is_deleted"]
    search_fields = ["share__investor_name_snapshot"]
    readonly_fields = ["created_by", "updated_by", "deleted_by", "created_at", "updated_at", "deleted_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ProfitFlow)
class ProfitFlowAdmin(admin.ModelAdmin):
    list_display = [
        "total_net_profit", "total_investor_profit_share", "total_owner_profit_share",
        "total_paid_out_to_investors", "total_reinvested_by_investors",
        "months_finalized_count", "last_updated_at",
    ]
    readonly_fields = [f.name for f in ProfitFlow._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
