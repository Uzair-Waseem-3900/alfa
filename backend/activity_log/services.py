from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .middleware import get_current_user
from .models import ActivityEvent, ActivityStatsFlow

_STAT_FIELD_BY_ACTION = {
    ActivityEvent.Action.CREATE:       "total_creates",
    ActivityEvent.Action.UPDATE:       "total_updates",
    ActivityEvent.Action.DELETE:       "total_deletes",
    ActivityEvent.Action.STATE_CHANGE: "total_state_changes",
}


def _increment_stats(action: str) -> None:
    """
    O(1) counter update via a single atomic UPDATE (F() expression) — no
    prior SELECT, no read-then-write race. Falls back to creating the
    singleton row only on the very first tracked event ever (get_or_create
    is idempotent under a race, since ActivityStatsFlow has a fixed pk=1).
    """
    stat_field = _STAT_FIELD_BY_ACTION[action]
    updated = ActivityStatsFlow.objects.filter(pk=1).update(
        total_events=F("total_events") + 1,
        last_event_at=timezone.now(),
        **{stat_field: F(stat_field) + 1},
    )
    if not updated:
        ActivityStatsFlow.objects.get_or_create(pk=1)
        ActivityStatsFlow.objects.filter(pk=1).update(
            total_events=F("total_events") + 1,
            last_event_at=timezone.now(),
            **{stat_field: F(stat_field) + 1},
        )


def is_tracking_enabled() -> bool:
    """
    O(1) — single indexed PK read, checked before any tracked write does
    real work. Cheaper by far than the INSERT + counter UPDATE it gates, so
    this check never becomes the cost it's protecting against. No row yet
    (brand-new install) means enabled — same "missing singleton = default
    state" convention as every other Flow row in this codebase.
    """
    value = ActivityStatsFlow.objects.filter(pk=1).values_list("is_enabled", flat=True).first()
    return value is not False


def set_tracking_enabled(*, enabled: bool, user) -> ActivityStatsFlow:
    """
    Flips the global on/off switch (superuser only, enforced at the view).

    Unlike every other write in this app, this call ALWAYS records its own
    ActivityEvent — it does NOT go through is_tracking_enabled()'s gate.
    A superuser silently disabling the audit trail with zero record of
    having done so would defeat the entire point of having one.
    """
    from django.db.models import F

    ActivityStatsFlow.objects.get_or_create(pk=1)
    actor = user if getattr(user, "is_authenticated", False) else None

    with transaction.atomic():
        ActivityEvent.objects.create(
            user=actor,
            action=ActivityEvent.Action.STATE_CHANGE,
            app_label="activity_log",
            model_name="activitystatsflow",
            object_id="1",
            object_repr="Activity Tracking",
            description=f"{'Enabled' if enabled else 'Disabled'} activity tracking",
            changed_fields=["is_enabled"],
        )
        ActivityStatsFlow.objects.filter(pk=1).update(
            is_enabled=enabled,
            enabled_toggled_by=actor,
            enabled_toggled_at=timezone.now(),
            total_events=F("total_events") + 1,
            total_state_changes=F("total_state_changes") + 1,
            last_event_at=timezone.now(),
        )
    return ActivityStatsFlow.get_instance()


def record_activity(*, action: str, instance, description: str, object_repr: str = "",
                     changed_fields=None, metadata=None) -> ActivityEvent | None:
    """
    THE single writer for ActivityEvent — called from activity_log.tracking's
    signal receivers (the normal path) or directly, if ever needed. Costs
    exactly one INSERT + one singleton UPDATE, regardless of table size —
    no query against the tracked model itself, no prior-state lookup.

    Wrapped in its own transaction.atomic(): this always runs from inside
    the caller's outer @transaction.atomic() business-write block (signals
    fire synchronously from within .save()), and every project convention
    puts writes inside atomic(). Nested atomic() becomes a real SAVEPOINT,
    so if this ever raises a genuine DB-level error (see object_id
    truncation below for why that's a real, not theoretical, case), only
    this savepoint rolls back — the outer business transaction is
    unaffected and can still commit. Without this, catching the exception
    in tracking.py's try/except would NOT be enough to protect the outer
    transaction: Postgres considers the whole transaction aborted the
    moment any statement inside it errors, so every later statement
    (including the outer COMMIT) would fail too, even though the Python
    exception was "handled."

    is_tracking_enabled()'s own SELECT is deliberately INSIDE this same
    savepoint, not before it — that read can fail too (e.g. mid-deploy,
    before this app's own migrations have run against a shared DB; a
    transient lock timeout), and if it raised outside the atomic block,
    the same "whole transaction aborted" problem above would apply to it
    just as much as to the INSERT it's guarding.
    """
    with transaction.atomic():
        if not is_tracking_enabled():
            return None

        user = get_current_user()
        user = user if getattr(user, "is_authenticated", False) else None

        event = ActivityEvent.objects.create(
            user=user,
            action=action,
            app_label=instance._meta.app_label,
            model_name=instance._meta.model_name,
            object_id=str(instance.pk)[:64] if instance.pk is not None else None,
            object_repr=object_repr[:255],
            description=description[:500],
            changed_fields=changed_fields or [],
            metadata=metadata or {},
        )
        _increment_stats(action)
    return event
