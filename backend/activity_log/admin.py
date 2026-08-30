from django.contrib import admin

from .models import ActivityEvent, ActivityStatsFlow


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display  = ["created_at", "user", "action", "app_label", "model_name", "object_repr"]
    list_filter   = ["action", "app_label"]
    search_fields = ["description", "object_repr"]
    readonly_fields = [f.name for f in ActivityEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ActivityStatsFlow)
class ActivityStatsFlowAdmin(admin.ModelAdmin):
    list_display = ["total_events", "total_creates", "total_updates", "total_deletes", "total_state_changes", "last_event_at", "is_enabled"]
    readonly_fields = [f.name for f in ActivityStatsFlow._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
