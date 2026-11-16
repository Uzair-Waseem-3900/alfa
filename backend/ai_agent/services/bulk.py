"""
Bulk invoices — everything that WRITES batch/row state (API side and worker side).

Rows are independent: one context-free agent run each, worked one after another by the `agent_bulk` queue.
A row's final status is decided HERE, in code, from the audit rows (AgentAction) and what the agent's two stop
tools recorded — never from the model's wording. "Done" therefore always means a draft really exists.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from billing.models import Invoice
from sales_man.selectors import get_link_name_by_id

from ..models import BulkBatch, BulkItem, ChatRun
from ..schemas.context import BulkOutcome
from ..selectors import bulk as sel

logger = logging.getLogger(__name__)

MSG_NO_REASON = "The assistant could not create this invoice and did not say why. Try again, or write the request more clearly."
MSG_STALE = "This row stopped unexpectedly (the worker was restarted?). Press Retry."
MSG_QUEUE = "Could not queue this row. Try again in a minute."
QUEUE_LOST_AFTER_SECONDS = 180
MSG_ATTEMPTS = "Too many tries for this row. Please create this invoice yourself in the Billing page."


# --------------------------------------------------------------------------- API side

def create_batch(*, user, prompts: list[str], link_name_id: int | None) -> BulkBatch:
    """Create the batch + its rows, then queue one task per row, in order."""
    link = None
    if link_name_id:
        try:
            link = get_link_name_by_id(link_name_id)
        except Exception:
            raise ValidationError({"link_name_id": ["That link name does not exist."]})
    with transaction.atomic():
        batch = BulkBatch.objects.create(user=user, link_name=link, link_name_label=link.name if link else "")
        BulkItem.objects.bulk_create(
            [BulkItem(batch=batch, position=n, prompt=text) for n, text in enumerate(prompts, start=1)]
        )
    enqueue_batch(batch.id)
    return batch


def _enqueue(item_ids) -> list[int]:
    """Queue the tasks; returns the ids that could NOT be queued (broker down)."""
    from ..tasks import run_bulk_item_task  # local: tasks imports services

    failed = []
    for item_id in item_ids:
        try:
            run_bulk_item_task.delay(item_id)
        except Exception:  # broker (Redis) down
            logger.exception("Could not queue bulk row %s", item_id)
            failed.append(item_id)
    return failed


def enqueue_batch(batch_id) -> None:
    ids = list(BulkItem.objects.filter(batch_id=batch_id, status=BulkItem.Status.QUEUED).order_by("position").values_list("id", flat=True))
    failed = _enqueue(ids)
    if failed:
        BulkItem.objects.filter(pk__in=failed, status=BulkItem.Status.QUEUED).update(
            status=BulkItem.Status.FAILED, message=MSG_QUEUE, finished_at=timezone.now())
        refresh_batch_status(batch_id)


def compose_prompt(item: BulkItem) -> str:
    """The row's prompt plus every earlier question and the user's answer (the agent keeps no history)."""
    if not item.answers:
        return item.prompt
    rounds = "\n".join(f"Q: {r['question']}\nA: {r['answer']}" for r in item.answers)
    return (f"{item.prompt}\n\n--- Earlier questions about THIS request and the user's answers "
            f"(the answers are the user's instructions) ---\n{rounds}")


def _refuse_if_cancelled(item: BulkItem) -> None:
    if item.batch.status == BulkBatch.Status.CANCELLED:
        raise ValidationError({"detail": "This batch was cancelled. Start a new batch for this invoice."})


def answer_item(*, item: BulkItem, answer: str) -> BulkItem:
    _refuse_if_cancelled(item)
    if item.status != BulkItem.Status.NEEDS_ATTENTION:
        raise ValidationError({"detail": "This invoice is not waiting for an answer."})
    if item.attempts >= settings.AGENT_BULK_MAX_ATTEMPTS:
        raise ValidationError({"detail": MSG_ATTEMPTS})
    rounds = list(item.answers) + [{"question": item.question, "answer": answer}]
    moved = BulkItem.objects.filter(pk=item.pk, status=BulkItem.Status.NEEDS_ATTENTION).update(
        status=BulkItem.Status.QUEUED, answers=rounds, question="", options=[], message="", updated_at=timezone.now())
    if not moved:   # double click / another tab
        raise ValidationError({"detail": "This invoice is not waiting for an answer."})
    BulkBatch.objects.filter(pk=item.batch_id).exclude(status=BulkBatch.Status.CANCELLED).update(
        status=BulkBatch.Status.ACTIVE, updated_at=timezone.now())
    _requeue(item.pk)
    item.refresh_from_db()
    return item


def retry_item(*, item: BulkItem) -> BulkItem:
    _refuse_if_cancelled(item)
    if item.status not in (BulkItem.Status.FAILED, BulkItem.Status.NOT_INVOICE):
        raise ValidationError({"detail": "Only a failed row can be retried."})
    if item.attempts >= settings.AGENT_BULK_MAX_ATTEMPTS:
        raise ValidationError({"detail": MSG_ATTEMPTS})
    action = sel.created_action(item_id=item.pk)
    if action:   # an earlier attempt DID create the draft before failing: never create a second one
        _mark_done(item.pk, action, only_from=(BulkItem.Status.FAILED, BulkItem.Status.NOT_INVOICE))
        refresh_batch_status(item.batch_id)
        item.refresh_from_db()
        return item
    moved = BulkItem.objects.filter(pk=item.pk, status=item.status).update(
        status=BulkItem.Status.QUEUED, message="", updated_at=timezone.now())
    if not moved:
        raise ValidationError({"detail": "This row changed; reload and try again."})
    BulkBatch.objects.filter(pk=item.batch_id).exclude(status=BulkBatch.Status.CANCELLED).update(
        status=BulkBatch.Status.ACTIVE, updated_at=timezone.now())
    _requeue(item.pk)
    item.refresh_from_db()
    return item


def _requeue(item_id) -> None:
    if _enqueue([item_id]):
        BulkItem.objects.filter(pk=item_id, status=BulkItem.Status.QUEUED).update(
            status=BulkItem.Status.FAILED, message=MSG_QUEUE, finished_at=timezone.now())


def skip_item(*, item: BulkItem) -> BulkItem:
    """'I'll do it myself': leave the row alone."""
    if item.status not in (BulkItem.Status.NEEDS_ATTENTION, BulkItem.Status.FAILED, BulkItem.Status.NOT_INVOICE):
        raise ValidationError({"detail": "Only a row that needs attention or failed can be skipped."})
    action = sel.created_action(item_id=item.pk)
    if action:   # a draft exists after all (e.g. a run that timed out still committed): report it, don't hide it
        _mark_done(item.pk, action, only_from=(item.status,))
        refresh_batch_status(item.batch_id)
        item.refresh_from_db()
        return item
    BulkItem.objects.filter(pk=item.pk, status=item.status).update(
        status=BulkItem.Status.SKIPPED, question="", options=[], updated_at=timezone.now(), finished_at=timezone.now())
    refresh_batch_status(item.batch_id)
    item.refresh_from_db()
    return item


def cancel_batch(*, batch: BulkBatch) -> BulkBatch:
    """Rows still waiting are cancelled; the row being processed finishes."""
    BulkItem.objects.filter(batch=batch, status=BulkItem.Status.QUEUED).update(
        status=BulkItem.Status.CANCELLED, updated_at=timezone.now(), finished_at=timezone.now())
    BulkBatch.objects.filter(pk=batch.pk).update(status=BulkBatch.Status.CANCELLED, updated_at=timezone.now())
    batch.refresh_from_db()
    return batch


def delete_batch(*, batch: BulkBatch) -> None:
    if sel.batch_is_active(batch.pk):
        raise ValidationError({"detail": "This batch is still working. Cancel it first."})
    batch.is_deleted = True
    batch.deleted_at = timezone.now()
    batch.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


def refresh_batch_status(batch_id) -> tuple[str, bool]:
    """-> (batch status, has_active_rows). Cancelled stays cancelled. The batch row is locked while the counts are
    read and the status written, so a worker finishing a row and a user answering another can't overwrite each other."""
    with transaction.atomic():
        batch = BulkBatch.all_objects.select_for_update().filter(pk=batch_id).first()
        if batch is None:
            return BulkBatch.Status.FINISHED, False
        counts = sel.status_counts(batch_id)
        active = any(counts.get(s, 0) for s in BulkItem.ACTIVE_STATUSES)
        if batch.status == BulkBatch.Status.CANCELLED:
            return batch.status, active
        if active:
            new = BulkBatch.Status.ACTIVE
        elif counts.get(BulkItem.Status.NEEDS_ATTENTION, 0):
            new = BulkBatch.Status.WAITING
        else:
            new = BulkBatch.Status.FINISHED
        if new != batch.status:
            BulkBatch.all_objects.filter(pk=batch_id).update(status=new, updated_at=timezone.now())
        return new, active


def resolve_stale_rows(batch_id) -> bool:
    """Rows stuck 'processing' (worker died): done if a draft was created, otherwise failed (retry offered)."""
    changed = False
    for item in sel.stale_processing_items(batch_id):
        action = sel.created_action(item_id=item.pk)
        if action:
            changed |= _mark_done(item.pk, action, only_from=(BulkItem.Status.PROCESSING,))
        else:
            changed |= bool(BulkItem.objects.filter(pk=item.pk, status=BulkItem.Status.PROCESSING).update(
                status=BulkItem.Status.FAILED, message=MSG_STALE, finished_at=timezone.now()))
        ChatRun.objects.filter(bulk_item=item, status__in=ChatRun.ACTIVE_STATUSES).update(
            status=ChatRun.Status.ERROR, error="Worker stopped.", finished_at=timezone.now())
    if changed:
        refresh_batch_status(batch_id)
    _requeue_lost_rows(batch_id)
    return changed


def _requeue_lost_rows(batch_id) -> None:
    """Nothing is processing but rows have been queued for a long while: their tasks were probably lost. Queue them
    again (claim_item's compare-and-set makes a duplicate delivery harmless). Touching updated_at limits this to
    once per QUEUE_LOST_AFTER_SECONDS, so a worker that is merely not running does not pile up duplicates."""
    counts = sel.status_counts(batch_id)
    if counts.get(BulkItem.Status.PROCESSING, 0) or not counts.get(BulkItem.Status.QUEUED, 0):
        return
    cutoff = timezone.now() - timedelta(seconds=QUEUE_LOST_AFTER_SECONDS)
    ids = list(BulkItem.objects.filter(batch_id=batch_id, status=BulkItem.Status.QUEUED, updated_at__lt=cutoff)
               .order_by("position").values_list("id", flat=True)[: settings.AGENT_BULK_MAX_ROWS])
    if not ids:
        return
    BulkItem.objects.filter(pk__in=ids, status=BulkItem.Status.QUEUED).update(updated_at=timezone.now())
    _enqueue(ids)


# --------------------------------------------------------------------------- worker side

def claim_item(item_id) -> BulkItem | None:
    """queued -> processing (compare-and-set: a duplicate delivery gets None). A cancelled/deleted batch cancels the row."""
    item = BulkItem.objects.select_related("batch", "batch__user").filter(pk=item_id).first()
    if item is None or item.status != BulkItem.Status.QUEUED:
        return None
    if item.batch.is_deleted or item.batch.status == BulkBatch.Status.CANCELLED:
        BulkItem.objects.filter(pk=item_id, status=BulkItem.Status.QUEUED).update(
            status=BulkItem.Status.CANCELLED, finished_at=timezone.now())
        return None
    claimed = BulkItem.objects.filter(pk=item_id, status=BulkItem.Status.QUEUED).update(
        status=BulkItem.Status.PROCESSING, started_at=timezone.now(), finished_at=None,
        attempts=F("attempts") + 1, updated_at=timezone.now())
    if not claimed:
        return None
    # re-fetch WITH the relations: the async worker must not lazy-load batch/user (refresh_from_db drops the cache)
    return BulkItem.objects.select_related("batch", "batch__user").get(pk=item_id)


def start_attempt(item: BulkItem) -> ChatRun:
    return ChatRun.objects.create(
        chat=None, bulk_item=item, user_message=compose_prompt(item),
        status=ChatRun.Status.RUNNING, started_at=timezone.now(),
    )


def _mark_done(item_id, action, *, only_from) -> bool:
    label = ""
    try:
        invoice = Invoice.objects.select_related("customer").only(
            "id", "customer__name", "customer__code").get(pk=action.invoice_id)
        label = f"{invoice.customer.name} ({invoice.customer.code})"
    except Invoice.DoesNotExist:
        pass
    return bool(BulkItem.objects.filter(pk=item_id, status__in=only_from).update(
        status=BulkItem.Status.DONE, bill_number=action.bill_number, invoice_id=action.invoice_id,
        customer_label=label[:300], question="", options=[], message="", finished_at=timezone.now(),
        updated_at=timezone.now()))


def finalize_item(*, item_id, run_id, outcome: BulkOutcome, final_text: str = "", error: str = "") -> BulkItem:
    """Decide the row's final state. Order matters: a draft that really exists always wins."""
    action = sel.created_action(run_id=run_id) if run_id else sel.created_action(item_id=item_id)
    if action:
        _mark_done(item_id, action, only_from=(BulkItem.Status.PROCESSING,))
        if run_id:
            ChatRun.objects.filter(pk=run_id).update(status=ChatRun.Status.DONE, finished_at=timezone.now())
    else:
        fields = dict(question="", options=[], message="", finished_at=timezone.now(), updated_at=timezone.now())
        if error:
            fields.update(status=BulkItem.Status.FAILED, message=error[:1000])
        elif outcome.question:
            fields.update(status=BulkItem.Status.NEEDS_ATTENTION, question=outcome.question, options=outcome.options,
                          finished_at=None)
        elif outcome.not_invoice:
            fields.update(status=BulkItem.Status.NOT_INVOICE, message=outcome.not_invoice)
        else:
            said = " ".join((final_text or "").split())[:300]
            fields.update(status=BulkItem.Status.FAILED, message=MSG_NO_REASON + (f" (It said: {said})" if said else ""))
        BulkItem.objects.filter(pk=item_id, status=BulkItem.Status.PROCESSING).update(**fields)
        if run_id:
            ChatRun.objects.filter(pk=run_id).update(
                status=ChatRun.Status.ERROR if error else ChatRun.Status.DONE, error=error[:1000], finished_at=timezone.now())
    return BulkItem.objects.get(pk=item_id)


def item_event(item: BulkItem) -> dict:
    return dict(
        item_id=item.pk, position=item.position, status=item.status, attempts=item.attempts, question=item.question,
        options=list(item.options or []), message=item.message, bill_number=item.bill_number,
        invoice_id=item.invoice_id, customer_label=item.customer_label,
    )
