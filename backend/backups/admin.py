from django.contrib import admin

from .models import BackupFlow, BackupHistory


@admin.register(BackupFlow)
class BackupFlowAdmin(admin.ModelAdmin):
    list_display = ["local_last_backup_at", "remote_last_backup_at"]
    readonly_fields = ["local_last_backup_at", "remote_last_backup_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BackupHistory)
class BackupHistoryAdmin(admin.ModelAdmin):
    list_display  = ["backup_type", "destination", "status", "covers_from", "covers_to", "row_count", "schema_migrated", "triggered_by", "created_at"]
    list_filter   = ["backup_type", "destination", "status"]
    readonly_fields = [f.name for f in BackupHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
