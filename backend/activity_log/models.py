from django.conf import settings
from django.db import models


class ActivityEvent(models.Model):
    """
    Append-only audit trail — one row per meaningful write to a "headline"
    business object (see activity_log.tracking.TRACKED_MODELS), across every
    app. Superuser-only. Never edited or deleted.

    Deliberately NOT populated via a blanket signal on every model: only the
    curated headline models are tracked, so a business action that touches
    several child rows (e.g. confirming a purchase order with 50 line items)
    produces exactly ONE event, not 50 — same granularity a hand-instrumented
    call site would have had, without needing one.

    description/metadata are built from field NAMES that changed
    (`update_fields`, when the caller provided it — which this codebase's
    services almost always do), not a before/after value diff — that
    deliberately avoids an extra SELECT per tracked write to fetch the prior
    row state, keeping the added cost to exactly one INSERT + one counter
    UPDATE per tracked write, regardless of table size.
    """

    class Action(models.TextChoices):
        CREATE       = "create",       "Create"
        UPDATE       = "update",       "Update"
        DELETE       = "delete",       "Delete"
        STATE_CHANGE = "state_change", "State Change"

    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="activity_events",
    )
    action      = models.CharField(max_length=20, choices=Action.choices, db_index=True)
    app_label   = models.CharField(max_length=50, db_index=True)
    model_name  = models.CharField(max_length=50, db_index=True)
    object_id   = models.CharField(max_length=64, null=True, blank=True)
    object_repr = models.CharField(max_length=255, blank=True, default="")
    description = models.CharField(max_length=500)
    # Field names touched (not values) — see class docstring. Never contains
    # a password/secret field's value, only its name if it changed.
    changed_fields = models.JSONField(default=list, blank=True)
    metadata       = models.JSONField(default=dict, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name        = "Activity Event"
        verbose_name_plural  = "Activity Events"
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["app_label", "model_name", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — {self.description}"


class ActivityStatsFlow(models.Model):
    """
    Single live record — all-time counts by action, kept in sync by
    activity_log.tracking's signal receiver on every tracked write. O(1)
    stats header for the activity log page: never a live Count() over
    ActivityEvent, no matter how large that table grows.
    """
    total_events        = models.PositiveIntegerField(default=0)
    total_creates        = models.PositiveIntegerField(default=0)
    total_updates         = models.PositiveIntegerField(default=0)
    total_deletes          = models.PositiveIntegerField(default=0)
    total_state_changes      = models.PositiveIntegerField(default=0)
    last_event_at        = models.DateTimeField(null=True, blank=True)

    # Global on/off switch, checked (one indexed PK read) before any tracked
    # write does real work — see services.is_tracking_enabled(). Toggling
    # this ALWAYS writes its own ActivityEvent (services.set_tracking_enabled),
    # bypassing the switch itself, so there's never a silent gap in who
    # turned auditing off/on.
    is_enabled          = models.BooleanField(default=True)
    enabled_toggled_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    enabled_toggled_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = "Activity Stats Flow"
        verbose_name_plural  = "Activity Stats Flow"

    def __str__(self):
        return f"ActivityStatsFlow — total {self.total_events}"

    @classmethod
    def get_instance(cls):
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance
