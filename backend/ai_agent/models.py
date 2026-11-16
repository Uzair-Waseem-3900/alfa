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
    # NULL for a bulk-invoice attempt (it has no chat; `bulk_item` says whose attempt it is).
    chat         = models.ForeignKey(Chat, null=True, blank=True, on_delete=models.CASCADE, related_name="runs")
    bulk_item    = models.ForeignKey("BulkItem", null=True, blank=True, on_delete=models.CASCADE, related_name="runs")
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
            models.UniqueConstraint(
                fields=["bulk_item"],
                condition=Q(status__in=["queued", "running"]),
                name="uniq_active_run_per_bulk_item",
            ),
        ]

    def __str__(self):
        return f"{self.id} [{self.status}]"


# ---------------------------------------------------------------------------
# AgentAction  (audit trail + idempotency for the assistant's WRITES)
# ---------------------------------------------------------------------------

class AgentAction(models.Model):
    """
    One row per change the assistant made to business data (currently: invoice
    drafts created / edited / discarded).

    Two jobs:
      * AUDIT — who asked (user), in which chat/run, what arguments, which
        invoice. `invoice_id` is a plain integer, deliberately NOT a foreign
        key: the audit trail must outlive the invoice and must not couple this
        app to billing's schema.
      * IDEMPOTENCY — unique per (run, tool, args_hash). If a run is retried
        after a cut-off model stream, the retried attempt repeats the same tool
        call; the partial unique index turns the repeat into "return what was
        already done" instead of a second invoice. (Rolling back the chat
        history does NOT undo database writes, so this is what prevents
        duplicates.)
    """

    class Result(models.TextChoices):
        CREATED   = "created", "Draft created"
        UPDATED   = "updated", "Draft updated"
        DISCARDED = "discarded", "Draft discarded"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="agent_actions",
    )
    chat = models.ForeignKey(Chat, null=True, on_delete=models.SET_NULL, related_name="actions")
    run  = models.ForeignKey(ChatRun, null=True, on_delete=models.SET_NULL, related_name="actions")
    tool = models.CharField(max_length=40)
    source      = models.CharField(max_length=8, default="chat")   # "chat" | "bulk": separate hourly write budgets
    args_hash   = models.CharField(max_length=64)
    arguments   = models.JSONField(default=dict)
    result      = models.CharField(max_length=12, choices=Result.choices)
    invoice_id  = models.PositiveIntegerField(null=True, blank=True)
    bill_number = models.CharField(max_length=30, blank=True, default="")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Agent Action"
        verbose_name_plural = "Agent Actions"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "tool", "args_hash"],
                condition=Q(run__isnull=False),
                name="uniq_agent_action_per_run",
            ),
        ]
        indexes = [
            # the hourly write-budget check: "this user's actions in the last hour"
            models.Index(fields=["user", "-created_at"], name="idx_agentaction_user_time"),
        ]

    def __str__(self):
        return f"{self.tool} {self.bill_number or ''} [{self.result}]"



# ---------------------------------------------------------------------------
# Bulk invoices  (many invoice requests, one context-free agent run each, queued)
# ---------------------------------------------------------------------------

class BulkBatch(models.Model):
    """
    A list of invoice prompts submitted together. Rows are worked one after another by the `agent_bulk`
    queue; the DATABASE is the source of truth (a Redis stream only carries live updates), so the owner
    can close the page and come back to the same state.
    """

    class Status(models.TextChoices):
        ACTIVE    = "active", "Working"            # at least one row queued or processing
        WAITING   = "waiting", "Needs your answers"  # nothing running; some rows need an answer
        FINISHED  = "finished", "Finished"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_bulk_batches")
    # Optional: customers are searched ONLY under this sales-man link name (the middle part of the customer code).
    link_name = models.ForeignKey("sales_man.SalesManLinkName", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    link_name_label = models.CharField(max_length=50, blank=True, default="")   # "FSD", kept even if the link name is removed later
    title = models.CharField(max_length=120, blank=True, default="")             # optional name the user gave it (rename)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    objects     = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        verbose_name = "Bulk Invoice Batch"
        verbose_name_plural = "Bulk Invoice Batches"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_bulkbatch_user_created"),
        ]

    def __str__(self):
        return f"{self.id} [{self.status}]"


class BulkItem(models.Model):
    """One invoice request inside a batch, with the question/answer rounds it needed."""

    class Status(models.TextChoices):
        QUEUED          = "queued", "Queued"
        PROCESSING      = "processing", "Processing"
        DONE            = "done", "Draft created"
        NEEDS_ATTENTION = "needs_attention", "Needs attention"
        NOT_INVOICE     = "not_invoice", "Not an invoice request"
        FAILED          = "failed", "Failed"
        SKIPPED         = "skipped", "Left for you"
        CANCELLED       = "cancelled", "Cancelled"

    ACTIVE_STATUSES = (Status.QUEUED, Status.PROCESSING)

    batch = models.ForeignKey(BulkBatch, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveIntegerField()
    prompt = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveIntegerField(default=0)
    question = models.TextField(blank=True, default="")
    options = models.JSONField(default=list, blank=True)            # quick answers offered with the question
    answers = models.JSONField(default=list, blank=True)            # [{"question": ..., "answer": ...}, ...]
    message = models.TextField(blank=True, default="")              # why it failed / is not an invoice request
    bill_number = models.CharField(max_length=30, blank=True, default="")
    invoice_id = models.PositiveIntegerField(null=True, blank=True)   # plain int: the audit outlives the invoice
    customer_label = models.CharField(max_length=300, blank=True, default="")   # who the draft went to ("NAME (CODE)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Bulk Invoice Row"
        verbose_name_plural = "Bulk Invoice Rows"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "position"], name="uniq_bulkitem_batch_position"),
        ]
        indexes = [
            models.Index(fields=["batch", "status"], name="idx_bulkitem_batch_status"),
        ]

    def __str__(self):
        return f"#{self.position} [{self.status}]"
