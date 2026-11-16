from django.contrib import admin

from .models import AgentAction, BulkBatch, BulkItem, Chat, ChatItem, ChatRun


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "updated_at", "is_deleted")
    list_filter = ("is_deleted",)
    raw_id_fields = ("user",)

    def get_queryset(self, request):
        return Chat.all_objects.all()


@admin.register(ChatRun)
class ChatRunAdmin(admin.ModelAdmin):
    list_display = ("id", "chat", "status", "created_at", "finished_at")
    list_filter = ("status",)
    raw_id_fields = ("chat", "bulk_item")


@admin.register(BulkBatch)
class BulkBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "link_name_label", "created_at", "is_deleted")
    list_filter = ("status", "is_deleted")
    raw_id_fields = ("user", "link_name")

    def get_queryset(self, request):
        return BulkBatch.all_objects.all()


@admin.register(BulkItem)
class BulkItemAdmin(admin.ModelAdmin):
    list_display = ("id", "batch", "position", "status", "attempts", "bill_number")
    list_filter = ("status",)
    raw_id_fields = ("batch",)


@admin.register(ChatItem)
class ChatItemAdmin(admin.ModelAdmin):
    list_display = ("id", "chat", "created_at")
    raw_id_fields = ("chat",)


@admin.register(AgentAction)
class AgentActionAdmin(admin.ModelAdmin):
    list_display = ("id", "tool", "result", "bill_number", "user", "created_at")
    list_filter = ("tool", "result")
    raw_id_fields = ("user", "chat", "run")
    readonly_fields = ("arguments",)

