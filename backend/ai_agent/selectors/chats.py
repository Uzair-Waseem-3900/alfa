"""
All READS for the chat tables. Every query is scoped to the owning user —
another user's chat/run is indistinguishable from a missing one (404).
"""
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from ..models import Chat, ChatItem, ChatRun


def get_user_chats(user) -> QuerySet:
    # Served by idx_chat_user_updated (user, -updated_at); soft-deleted rows
    # are excluded by Chat.objects.
    return Chat.objects.filter(user=user).only("id", "title", "created_at", "updated_at")


def get_user_chat(user, chat_id) -> Chat:
    return get_object_or_404(Chat.objects.filter(user=user), pk=chat_id)


def get_visible_messages(chat: Chat) -> QuerySet:
    """User + assistant messages only, newest first (page 1 = latest).
    Served by idx_chatitem_chat_kind_id."""
    return (
        ChatItem.objects
        .filter(chat=chat, kind__in=[ChatItem.Kind.USER, ChatItem.Kind.ASSISTANT])
        .only("id", "kind", "text", "created_at")
        .order_by("-id")
    )


def get_user_run(user, run_id) -> ChatRun:
    return get_object_or_404(
        ChatRun.objects.select_related("chat", "chat__user"),
        pk=run_id, chat__user=user, chat__is_deleted=False,
    )
