from django.contrib import admin

from .models import (
    Customer, FIFOLedger, Invoice, InvoiceItem,
    Payment, Return, ReturnItem,
)


class AuditAdminMixin:
    readonly_fields = (
        "created_by", "updated_by", "deleted_by",
        "created_at", "updated_at", "deleted_at",
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


class SoftDeleteAdminMixin:
    def get_queryset(self, request):
        return self.model.all_objects.all()


# ---------------------------------------------------------------------------

@admin.register(Customer)
class CustomerAdmin(AuditAdminMixin, SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ["name", "code", "mobile", "is_deleted", "created_at"]
    search_fields = ["name", "code", "mobile"]
    list_filter = ["is_deleted"]
    readonly_fields = AuditAdminMixin.readonly_fields


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = [
        "product", "quantity", "returned_quantity",
        "selling_price", "cogs_per_unit",
        "line_total", "line_cogs", "line_profit",
    ]
    can_delete = False


@admin.register(Invoice)
class InvoiceAdmin(AuditAdminMixin, SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = [
        "bill_number", "customer", "status",
        "subtotal", "gross_profit", "is_deleted", "created_at",
    ]
    list_filter = ["status", "is_deleted"]
    search_fields = ["bill_number", "customer__name", "customer__code"]
    readonly_fields = AuditAdminMixin.readonly_fields + (
        "bill_number", "status", "confirmed_by", "confirmed_at",
        "subtotal", "total_cogs", "gross_profit",
    )
    inlines = [InvoiceItemInline]


@admin.register(FIFOLedger)
class FIFOLedgerAdmin(admin.ModelAdmin):
    list_display = ["invoice_item", "purchase", "quantity", "unit_cost", "created_at"]
    readonly_fields = ["invoice_item", "purchase", "quantity", "unit_cost", "created_at"]
    list_filter = ["created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(AuditAdminMixin, SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ["invoice", "amount", "method", "payment_date", "is_deleted", "created_at"]
    list_filter = ["method", "is_deleted"]
    search_fields = ["invoice__bill_number"]
    readonly_fields = AuditAdminMixin.readonly_fields


class ReturnItemInline(admin.TabularInline):
    model = ReturnItem
    extra = 0
    readonly_fields = [
        "invoice_item", "quantity",
        "selling_price", "cogs_per_unit", "line_total", "line_cogs",
    ]
    can_delete = False


@admin.register(Return)
class ReturnAdmin(AuditAdminMixin, SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = [
        "invoice", "status", "total_return_amount",
        "accepted_by", "accepted_at", "created_at",
    ]
    list_filter = ["status"]
    search_fields = ["invoice__bill_number"]
    readonly_fields = AuditAdminMixin.readonly_fields + (
        "status", "accepted_by", "accepted_at",
        "total_return_amount", "total_return_cogs",
    )
    inlines = [ReturnItemInline]