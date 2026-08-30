from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from backend.search import search_q

from .models import ActivityEvent, ActivityStatsFlow

# The quick filter a superuser reaches for first when hunting for something
# suspicious: every delete, plus updates/state-changes to the money-moving
# or pricing-sensitive models.
_HIGH_RISK_MODELS = {
    "productrate", "purchaseorder", "purchasereturn", "invoice", "return",
    "supplierpayment", "payment", "cashadjustment", "taxpayment", "whtpayment",
    "investortransaction", "ownertransaction", "user",
}


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


# `created_at__date=...` defeats the index on a DateTimeField (see
# architecture.md) — these convert a YYYY-MM-DD string into aware datetime
# bounds instead, same pattern as purchases.selectors._day_start.

def _day_start(value):
    day = parse_date(str(value))
    if day is None:
        return None
    return timezone.make_aware(datetime.combine(day, time.min))


def _next_day_start(value):
    day = parse_date(str(value))
    if day is None:
        return None
    return timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))


def get_activity_events(
    *, user_id: str = None, action: str = None, app_label: str = None,
    model_name: str = None, search: str = None, date_from: str = None, date_to: str = None,
    high_risk: bool = False,
):
    """
    Paginated, indexed activity feed for the superuser-only audit page.
    Every filter here hits an indexed column (user/-created_at,
    action/-created_at, app_label+model_name/-created_at) or the trigram
    index on description/object_repr for `search` — never a table scan
    regardless of how large the table grows.
    """
    qs = ActivityEvent.objects.select_related("user").order_by("-created_at")

    if _clean(user_id):
        qs = qs.filter(user_id=_clean(user_id))
    if _clean(action):
        qs = qs.filter(action=_clean(action))
    if _clean(app_label):
        qs = qs.filter(app_label=_clean(app_label))
    if _clean(model_name):
        qs = qs.filter(model_name=_clean(model_name))
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "description", "object_repr"))
    if _clean(date_from):
        start = _day_start(_clean(date_from))
        if start:
            qs = qs.filter(created_at__gte=start)
    if _clean(date_to):
        end = _next_day_start(_clean(date_to))
        if end:
            qs = qs.filter(created_at__lt=end)
    if high_risk:
        qs = qs.filter(Q(action=ActivityEvent.Action.DELETE) | Q(model_name__in=_HIGH_RISK_MODELS))

    return qs


def get_activity_stats():
    """O(1) — one row read, never a live Count() over ActivityEvent."""
    return ActivityStatsFlow.get_instance()
