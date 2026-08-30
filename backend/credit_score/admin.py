from django.contrib import admin

from .models import CreditScoreFlow, CreditScoreHistory, CustomerCreditScore


@admin.register(CreditScoreFlow)
class CreditScoreFlowAdmin(admin.ModelAdmin):
    list_display = ["overdue_caught_up_through", "last_updated_at"]
    readonly_fields = [f.name for f in CreditScoreFlow._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CustomerCreditScore)
class CustomerCreditScoreAdmin(admin.ModelAdmin):
    list_display = ["customer", "score", "tier", "last_calculated_at"]
    list_filter = ["tier"]
    search_fields = ["customer__name", "customer__code"]
    readonly_fields = [f.name for f in CustomerCreditScore._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(CreditScoreHistory)
class CreditScoreHistoryAdmin(admin.ModelAdmin):
    list_display = ["customer", "score_before", "score_after", "trigger", "created_at"]
    list_filter = ["trigger"]
    search_fields = ["customer__name", "customer__code", "reference"]
    readonly_fields = [f.name for f in CreditScoreHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
