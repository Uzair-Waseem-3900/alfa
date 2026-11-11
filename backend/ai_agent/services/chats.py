"""All WRITES for chats (soft delete, never a hard delete)."""
from django.db import transaction
from django.utils import timezone

from ..models import Chat


@transaction.atomic
def create_chat(*, user, title: str = "") -> Chat:
    return Chat.objects.create(user=user, title=(title or "New chat")[:120])


@transaction.atomic
def rename_chat(*, chat: Chat, title: str) -> Chat:
    chat.title = title
    chat.save(update_fields=["title", "updated_at"])
    return chat


@transaction.atomic
def soft_delete_chat(*, chat: Chat) -> None:
    chat.is_deleted = True
    chat.deleted_at = timezone.now()
    chat.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
