"""READS for bulk invoices. Every query is scoped to the owning user (another user's batch is a 404)."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Max, Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone

from sales_man.selectors import get_all_link_names

from ..models import AgentAction, BulkBatch, BulkItem


def _with_counts(qs: QuerySet) -> QuerySet:
    return (
        qs.annotate(
            total=Count("items"),
            done=Count("items", filter=Q(items__status=BulkItem.Status.DONE)),
            attention=Count("items", filter=Q(items__status=BulkItem.Status.NEEDS_ATTENTION)),
            failed=Count("items", filter=Q(items__status__in=[BulkItem.Status.FAILED, BulkItem.Status.NOT_INVOICE])),
            working=Count("items", filter=Q(items__status__in=BulkItem.ACTIVE_STATUSES)),
        )
        .order_by("-created_at")
    )


def get_user_batches(user) -> QuerySet:
    """My batches newest first with row counts in ONE grouped query (served by idx_bulkbatch_user_created
    + idx_bulkitem_batch_status). Paginated by the view."""
    return _with_counts(BulkBatch.objects.filter(user=user))


# ---- team view (superuser, READ ONLY): every user's non-deleted batches -------------------------------------

def get_batch_owners() -> QuerySet:
    """One row per user who has bulk batches, most recently active first (one GROUP BY; paginated by the view)."""
    return (
        BulkBatch.objects
        .values("user", "user__first_name", "user__last_name", "user__is_superuser")
        .annotate(batch_count=Count("id"), last_active=Max("updated_at"))
        .order_by("-last_active", "user")
    )


def get_batches_of_owner(email: str) -> QuerySet:
    """Any one user's batches, newest first, with row counts (idx_bulkbatch_user_created). Superuser views only."""
    return _with_counts(BulkBatch.objects.filter(user_id=email).select_related("user"))


def get_any_batch_with_items(batch_id) -> BulkBatch:
    """A batch of ANY owner with its rows in 3 queries. Superuser views only: never use it for the owner endpoints."""
    return get_object_or_404(BulkBatch.objects.select_related("user").prefetch_related("items"), pk=batch_id)


def get_user_batch(user, batch_id) -> BulkBatch:
    return get_object_or_404(BulkBatch.objects.filter(user=user), pk=batch_id)


def get_user_batch_with_items(user, batch_id) -> BulkBatch:
    """Batch + its rows in 2 queries (rows are capped by AGENT_BULK_MAX_ROWS)."""
    return get_object_or_404(BulkBatch.objects.filter(user=user).prefetch_related("items"), pk=batch_id)


def get_user_item(user, item_id) -> BulkItem:
    return get_object_or_404(
        BulkItem.objects.select_related("batch"), pk=item_id, batch__user=user, batch__is_deleted=False,
    )


def stale_processing_items(batch_id) -> list[BulkItem]:
    """Rows 'processing' for longer than the worker timeout: the worker that held them died."""
    cutoff = timezone.now() - timedelta(seconds=settings.AGENT_BULK_ITEM_TIMEOUT_SECONDS + 60)
    return list(BulkItem.objects.filter(batch_id=batch_id, status=BulkItem.Status.PROCESSING, started_at__lt=cutoff))


def status_counts(batch_id) -> dict:
    return {r["status"]: r["n"] for r in BulkItem.objects.filter(batch_id=batch_id).values("status").annotate(n=Count("id"))}


def count_active_rows(user) -> int:
    """Rows of this user still queued/processing. Only the user's ACTIVE batches are looked at
    (idx_bulkbatch_user_created, then idx_bulkitem_batch_status), never the whole history."""
    active_batches = BulkBatch.objects.filter(user=user, status=BulkBatch.Status.ACTIVE).values("id")
    return BulkItem.objects.filter(batch_id__in=active_batches, status__in=BulkItem.ACTIVE_STATUSES).count()


def batch_is_active(batch_id) -> bool:
    return BulkItem.objects.filter(batch_id=batch_id, status__in=BulkItem.ACTIVE_STATUSES).exists()


def created_action(*, run_id=None, item_id=None):
    """The 'created' audit row proving a draft exists for this run (or any attempt of this row)."""
    qs = AgentAction.objects.filter(result=AgentAction.Result.CREATED)
    if run_id:
        qs = qs.filter(run_id=run_id)
    elif item_id:
        qs = qs.filter(run__bulk_item_id=item_id)
    else:
        return None
    return qs.order_by("id").first()


def link_names():
    return get_all_link_names()
