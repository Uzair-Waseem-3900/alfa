"""Run lifecycle: start (API side) and status transitions (worker side)."""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from ..models import Chat, ChatItem, ChatRun

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "New chat"


class AgentUnavailable(APIException):
    status_code = 503
    default_detail = "The assistant is temporarily unavailable. Please try again."
    default_code = "agent_unavailable"


def _expire_stale_runs(chat: Chat) -> None:
    """A worker that died mid-run would leave its chat 'busy' forever. Any
    active run older than the Celery hard time limit can no longer be alive."""
    cutoff = timezone.now() - timedelta(seconds=settings.CELERY_TASK_TIME_LIMIT + 60)
    ChatRun.objects.filter(
        chat=chat, status__in=ChatRun.ACTIVE_STATUSES, created_at__lt=cutoff,
    ).update(status=ChatRun.Status.ERROR, error="Timed out.", finished_at=timezone.now())


def start_run(*, chat: Chat, content: str) -> ChatRun:
    """Create the run row and queue the Celery task. One active run per chat:
    the partial UniqueConstraint decides races, and the loser gets the same
    clean 400 the pre-check would give (architecture.md: check-then-act)."""
    from ..tasks import run_agent_task  # local: tasks imports services

    def create():
        with transaction.atomic():  # savepoint so the IntegrityError is recoverable
            run = ChatRun.objects.create(chat=chat, user_message=content)
            if chat.title == DEFAULT_TITLE and not ChatItem.objects.filter(chat=chat).exists():
                chat.title = content[:60]
                chat.save(update_fields=["title", "updated_at"])
            return run

    try:
        run = create()
    except IntegrityError:
        # Busy: either a genuinely live run, or a dead one past the time limit.
        # Only pay for the stale-run sweep on this (rare) path, then retry once.
        _expire_stale_runs(chat)
        try:
            run = create()
        except IntegrityError:
            raise ValidationError({"detail": "A reply is already being generated for this chat."})

    try:
        run_agent_task.delay(str(run.id))
    except Exception:  # broker (Redis) down
        logger.exception("Could not queue agent run %s", run.id)
        mark_error(run.id, "Could not queue the request.")
        raise AgentUnavailable()
    return run


# --- worker-side transitions -------------------------------------------------

def mark_running(run_id) -> bool:
    """queued -> running. False if it was not queued (duplicate delivery)."""
    return bool(ChatRun.objects.filter(pk=run_id, status=ChatRun.Status.QUEUED).update(
        status=ChatRun.Status.RUNNING, started_at=timezone.now(),
    ))


def mark_done(run_id) -> None:
    ChatRun.objects.filter(pk=run_id).update(status=ChatRun.Status.DONE, finished_at=timezone.now())


def mark_error(run_id, message: str) -> None:
    ChatRun.objects.filter(pk=run_id).update(
        status=ChatRun.Status.ERROR, error=message[:1000], finished_at=timezone.now(),
    )
