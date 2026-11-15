from django.contrib import admin

from .models import AgentAction, Chat, ChatItem, ChatRun


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
    raw_id_fields = ("chat",)


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

