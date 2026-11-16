"""
All READS for the chat tables. Every query is scoped to the owning user —
another user's chat/run is indistinguishable from a missing one (404).
"""
from django.db.models import Count, Max, QuerySet
from django.shortcuts import get_object_or_404

from ..models import Chat, ChatItem, ChatRun


def get_user_chats(user) -> QuerySet:
    # Served by idx_chat_user_updated (user, -updated_at); soft-deleted rows
    # are excluded by Chat.objects.
    return Chat.objects.filter(user=user).only("id", "title", "created_at", "updated_at")


def get_user_chat(user, chat_id) -> Chat:
    return get_object_or_404(Chat.objects.filter(user=user), pk=chat_id)


def get_chat_owners() -> QuerySet:
    """Team chats (superuser, read-only): one row per user who has chats, most recently active first.
    One GROUP BY over the chat table, served by idx_chat_user_updated; paginated by the view."""
    return (
        Chat.objects
        .values("user", "user__first_name", "user__last_name", "user__is_superuser")
        .annotate(chat_count=Count("id"), last_active=Max("updated_at"))
        .order_by("-last_active", "user")
    )


def get_chats_of_owner(email: str) -> QuerySet:
    """Any one user's live chats, newest first (idx_chat_user_updated). Superuser views only."""
    return (
        Chat.objects.filter(user_id=email)
        .select_related("user")
        .only("id", "title", "created_at", "updated_at", "user__email", "user__first_name", "user__last_name")
    )


def get_any_chat(chat_id) -> Chat:
    """A live chat of ANY owner (superuser views only — never use this for the owner's own endpoints)."""
    return get_object_or_404(Chat.objects.select_related("user"), pk=chat_id)


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
