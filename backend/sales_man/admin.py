from django.contrib import admin

from .models import SalesMan, SalesManLinkName


class SalesManLinkNameInline(admin.TabularInline):
    model = SalesManLinkName
    extra = 0
    fields = ["name", "is_deleted"]
    readonly_fields = ["name", "is_deleted"]
    can_delete = False


@admin.register(SalesMan)
class SalesManAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "total_customers", "total_outstanding", "is_deleted"]
    list_filter = ["is_deleted"]
    search_fields = ["name", "code"]
    readonly_fields = [
        "total_customers", "total_outstanding",
        "created_by", "updated_by", "deleted_by", "created_at", "updated_at", "deleted_at",
    ]
    inlines = [SalesManLinkNameInline]


@admin.register(SalesManLinkName)
class SalesManLinkNameAdmin(admin.ModelAdmin):
    list_display = ["name", "sales_man", "is_deleted"]
    list_filter = ["is_deleted"]
    search_fields = ["name", "sales_man__name"]
    readonly_fields = [
        "created_by", "updated_by", "deleted_by", "created_at", "updated_at", "deleted_at",
    ]
