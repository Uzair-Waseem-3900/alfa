from django.contrib import admin

from .models import AccountTransfer, PaymentAllocation, PaymentMethod


class AuditAdminMixin:
    readonly_fields = ("created_by", "updated_by", "deleted_by", "created_at", "updated_at", "deleted_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display  = ["name", "account_number", "balance", "is_protected", "is_deleted"]
    list_filter   = ["is_protected", "is_deleted"]
    search_fields = ["name", "account_number"]
    readonly_fields = AuditAdminMixin.readonly_fields + ("balance",)


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display  = ["payment_method", "direction", "amount", "date", "source_model", "source_id", "is_deleted"]
    list_filter   = ["direction", "is_deleted", "source_model"]
    search_fields = ["source_model"]
    readonly_fields = [f.name for f in PaymentAllocation._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AccountTransfer)
class AccountTransferAdmin(AuditAdminMixin, admin.ModelAdmin):
    list_display  = ["from_method", "to_method", "amount", "date", "is_deleted"]
    list_filter   = ["is_deleted"]
    search_fields = ["note"]
