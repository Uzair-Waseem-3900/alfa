from django.contrib import admin

from .models import TaxFlow, TaxPayment, WHTPayment


@admin.register(TaxFlow)
class TaxFlowAdmin(admin.ModelAdmin):
    list_display = [
        "total_input_tax_paid", "total_output_tax_collected",
        "net_sales_tax_payable", "total_sales_tax_paid", "sales_tax_outstanding",
        "total_wht_withheld_from_suppliers", "total_wht_withheld_by_customers",
        "total_wht_paid", "wht_outstanding",
        "last_updated_at",
    ]
    readonly_fields = [f.name for f in TaxFlow._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TaxPayment)
class TaxPaymentAdmin(admin.ModelAdmin):
    list_display  = ["amount", "payment_date", "is_deleted", "created_by", "created_at"]
    list_filter   = ["is_deleted"]
    search_fields = ["note"]
    readonly_fields = ["created_by", "updated_by", "deleted_by", "created_at", "updated_at", "deleted_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(WHTPayment)
class WHTPaymentAdmin(admin.ModelAdmin):
    list_display  = ["amount", "payment_date", "is_deleted", "created_by", "created_at"]
    list_filter   = ["is_deleted"]
    search_fields = ["note"]
    readonly_fields = ["created_by", "updated_by", "deleted_by", "created_at", "updated_at", "deleted_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)
