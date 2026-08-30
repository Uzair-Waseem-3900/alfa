from django.contrib import admin

from .models import BalanceSheetSnapshot


@admin.register(BalanceSheetSnapshot)
class BalanceSheetSnapshotAdmin(admin.ModelAdmin):
    list_display = ("period", "total_assets", "total_liabilities", "total_equity", "computed_at")
    ordering = ("-period",)
