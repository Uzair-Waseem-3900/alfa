"""Turn a PeriodName (+ optional custom dates) into a validated date range.
"today" is always the Asia/Karachi calendar day — timezone.localdate(), never
timezone.now().date() (architecture.md date rule)."""
from datetime import date, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date
from pydantic import ValidationError

from ..schemas.tools import PeriodName, PeriodRange
from .base import ToolInputError


def _parse(value: str | None, field: str) -> date:
    try:
        d = parse_date(value) if value else None
    except ValueError:   # well-formed but impossible, e.g. 2026-02-30 / 2026-13-01
        d = None
    if d is None:
        raise ToolInputError(f"{field} must be a date in YYYY-MM-DD format for a custom period.")
    return d


def resolve_period(period: PeriodName, date_from: str | None = None, date_to: str | None = None) -> PeriodRange:
    today = timezone.localdate()

    if period == "custom":
        start, end = _parse(date_from, "date_from"), _parse(date_to, "date_to")
        label = f"{start:%d %b %Y} to {end:%d %b %Y}"
    elif period == "all_time":
        start = end = None
        label = "all time"
    elif period == "today":
        start = end = today
        label = f"today ({today:%d %b %Y})"
    elif period == "yesterday":
        start = end = today - timedelta(days=1)
        label = f"yesterday ({start:%d %b %Y})"
    elif period == "last_7_days":
        start, end, label = today - timedelta(days=6), today, "last 7 days"
    elif period == "last_30_days":
        start, end, label = today - timedelta(days=29), today, "last 30 days"
    elif period == "this_week":
        start, end, label = today - timedelta(days=today.weekday()), today, "this week (Mon-today)"
    elif period == "this_month":
        start, end, label = today.replace(day=1), today, f"this month ({today:%b %Y})"
    elif period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        start, label = end.replace(day=1), f"last month ({end:%b %Y})"
    elif period == "this_year":
        start, end, label = today.replace(month=1, day=1), today, f"this year ({today.year})"
    elif period == "last_year":
        start, end = date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
        label = f"last year ({today.year - 1})"
    else:  # unreachable: the Literal restricts it
        raise ToolInputError(f"Unknown period '{period}'.")

    try:
        return PeriodRange(label=label, date_from=start, date_to=end)
    except ValidationError as exc:
        raise ToolInputError(exc.errors()[0]["msg"].removeprefix("Value error, "))
