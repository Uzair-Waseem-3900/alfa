import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


# ---------------------------------------------------------------------------
# Soft-delete infrastructure (mirrors billing/payment_methods models)
# ---------------------------------------------------------------------------

class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset()


# ---------------------------------------------------------------------------
# Chat  (one conversation, owned by exactly one user)
# ---------------------------------------------------------------------------

class Chat(models.Model):
    """
    A chat belongs to ONE user; no other user can ever read it (every
    selector filters on `user`). UUID primary key so ids can't be guessed
    or enumerated.

    `updated_at` is indexed because the chat list is ordered by it, and the
    composite index (user, -updated_at) serves "my chats, newest first" as a
    single index range scan.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_chats",
    )
    title = models.CharField(max_length=120, default="New chat")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False, db_index=True)

    objects     = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        verbose_name        = "Chat"
        verbose_name_plural = "Chats"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at"], name="idx_chat_user_updated"),
        ]

    def __str__(self):
        return f"{self.title} ({self.user_id})"


# ---------------------------------------------------------------------------
# ChatItem  (the agent's memory — one row per OpenAI-Agents-SDK session item)
# ---------------------------------------------------------------------------

class ChatItem(models.Model):
    """
    One SDK "input item" (user message, assistant message, tool call, tool
    output) stored as JSON. This is the SINGLE source of truth for both the
    agent's memory and the visible chat history — the history endpoint
    derives user/assistant messages from it, so nothing is stored twice.

    Append-only, ordered by id. Never edited, so no soft delete: rows go
    away only with their chat (chats themselves are soft-deleted).
    """

    class Kind(models.TextChoices):
        USER      = "user", "User message"
        ASSISTANT = "assistant", "Assistant message"
        OTHER     = "other", "Tool call / tool output"   # hidden from the visible history

    chat       = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="items")
    payload    = models.JSONField()
    # Derived once at write time from `payload` (by services.session) so the
    # history endpoint can paginate ONLY visible messages with an indexed
    # filter instead of scanning tool rows or parsing JSON in SQL/Python.
    kind       = models.CharField(max_length=10, choices=Kind.choices, default=Kind.OTHER)
    text       = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Chat Item"
        verbose_name_plural = "Chat Items"
        ordering = ["id"]
        indexes = [
            models.Index(fields=["chat", "id"], name="idx_chatitem_chat_id"),
            models.Index(fields=["chat", "kind", "id"], name="idx_chatitem_chat_kind_id"),
        ]


# ---------------------------------------------------------------------------
# ChatRun  (one question → answer execution, tracked for the SSE stream)
# ---------------------------------------------------------------------------

class ChatRun(models.Model):
    """
    One Celery execution answering one user message. Its id names the Redis
    stream the SSE endpoint reads.

    At most ONE active (queued/running) run per chat — enforced by a partial
    UniqueConstraint so two near-simultaneous sends can't both start; the
    losing request gets a clean 400 (services.runs catches IntegrityError).
    """

    class Status(models.TextChoices):
        QUEUED  = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE    = "done", "Done"
        ERROR   = "error", "Error"

    ACTIVE_STATUSES = (Status.QUEUED, Status.RUNNING)

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chat         = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name="runs")
    user_message = models.TextField()
    status       = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    error        = models.TextField(blank=True, default="")

    created_at  = models.DateTimeField(auto_now_add=True)
    started_at  = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = "Chat Run"
        verbose_name_plural = "Chat Runs"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["chat"],
                condition=Q(status__in=["queued", "running"]),
                name="uniq_active_run_per_chat",
            ),
        ]

    def __str__(self):
        return f"{self.id} [{self.status}]"
