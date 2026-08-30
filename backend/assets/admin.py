from django.contrib import admin

from .models import Asset, AssetCategory, AssetDisposal, AssetFlow, AssetValuationEntry


@admin.register(AssetFlow)
class AssetFlowAdmin(admin.ModelAdmin):
    list_display = [
        "total_asset_cost", "total_current_worth", "total_accumulated_depreciation",
        "total_disposed_count", "total_gain_on_disposal", "total_loss_on_disposal",
        "last_updated_at",
    ]
    readonly_fields = [f.name for f in AssetFlow._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AssetCategory)
class AssetCategoryAdmin(admin.ModelAdmin):
    list_display  = ["name", "valuation_method", "depreciation_rate"]
    list_filter   = ["valuation_method"]
    search_fields = ["name"]
    readonly_fields = ["valuation_method", "created_by", "created_at"]


class AssetValuationEntryInline(admin.TabularInline):
    model           = AssetValuationEntry
    extra           = 0
    readonly_fields = ["entry_type", "period", "rate_applied", "worth_before", "worth_after", "amount", "note", "created_by", "created_at"]
    can_delete      = False


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display  = ["name", "category", "acquisition_type", "cost", "current_worth", "is_disposed", "is_deleted"]
    list_filter   = ["category", "acquisition_type", "is_disposed", "is_deleted"]
    search_fields = ["name"]
    readonly_fields = ["created_by", "updated_by", "deleted_by", "created_at", "updated_at", "deleted_at"]
    inlines = [AssetValuationEntryInline]


@admin.register(AssetValuationEntry)
class AssetValuationEntryAdmin(admin.ModelAdmin):
    list_display  = ["asset", "entry_type", "period", "rate_applied", "amount", "worth_after"]
    list_filter   = ["entry_type"]
    search_fields = ["asset__name"]
    readonly_fields = [f.name for f in AssetValuationEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AssetDisposal)
class AssetDisposalAdmin(admin.ModelAdmin):
    list_display  = ["asset", "disposal_type", "disposal_date", "sale_amount", "gain_loss"]
    list_filter   = ["disposal_type"]
    search_fields = ["asset__name"]
    readonly_fields = [f.name for f in AssetDisposal._meta.fields]

    def has_add_permission(self, request):
        return False
