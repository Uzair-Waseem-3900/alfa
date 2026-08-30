from django.contrib import admin

from .models import (
    CustomerOpeningBalance, OpeningCashEntry, SupplierOpeningBalance,
)


class _ReadOnlyAdmin(admin.ModelAdmin):
    """Audit-only: opening records are permanently locked (no add/change/delete)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SupplierOpeningBalance)
class SupplierOpeningBalanceAdmin(_ReadOnlyAdmin):
    list_display = ("id", "supplier", "amount", "purchase_order", "created_by", "created_at")
    search_fields = ("supplier__name", "supplier__code")


@admin.register(CustomerOpeningBalance)
class CustomerOpeningBalanceAdmin(_ReadOnlyAdmin):
    list_display = ("id", "customer", "amount", "invoice", "created_by", "created_at")
    search_fields = ("customer__name", "customer__code")


@admin.register(OpeningCashEntry)
class OpeningCashEntryAdmin(_ReadOnlyAdmin):
    list_display = ("id", "amount", "added_by", "added_at")
