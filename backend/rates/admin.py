from django.contrib import admin

from .models import ProductRate, ProductRateHistory, UnpricedProduct


@admin.register(ProductRate)
class ProductRateAdmin(admin.ModelAdmin):
    list_display = ["product", "selling_price", "updated_by", "updated_at", "created_at"]
    search_fields = ["product__name", "product__code"]
    list_filter = ["product__category"]
    readonly_fields = ["created_by", "updated_by", "created_at", "updated_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        # Rates are never deleted — only updated
        return False


@admin.register(UnpricedProduct)
class UnpricedProductAdmin(admin.ModelAdmin):
    list_display = ["product", "created_at"]
    search_fields = ["product__name", "product__code"]
    list_filter = ["product__category"]
    readonly_fields = ["product", "created_at"]

    def has_add_permission(self, request):
        # Kept in sync by services only — never manually created/edited.
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProductRateHistory)
class ProductRateHistoryAdmin(admin.ModelAdmin):
    list_display = ["product", "selling_price", "changed_by", "changed_at", "note"]
    search_fields = ["product__name", "product__code"]
    list_filter = ["product__category", "changed_at"]
    readonly_fields = ["product", "selling_price", "changed_by", "changed_at", "note"]

    def has_add_permission(self, request):
        # History is append-only via services — never manually created
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False