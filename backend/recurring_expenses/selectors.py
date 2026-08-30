from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from backend.search import search_q

from .models import (
    RecurringExpense, RecurringExpenseAssignment, RecurringExpenseAssignmentPayment,
    RecurringExpenseCategory, RecurringExpenseFlow, RecurringExpenseMonthlyStats,
)


def _clean(value):
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


# ---------------------------------------------------------------------------
# RecurringExpenseCategory
# ---------------------------------------------------------------------------

def get_all_recurring_expense_categories(*, search: str = None) -> QuerySet:
    # created_by is serialized on every row — select_related avoids one
    # extra query per category (N+1).
    qs = RecurringExpenseCategory.objects.filter(is_deleted=False).select_related("created_by")
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name"))
    return qs.order_by("name")


def get_recurring_expense_category_by_id(pk: int) -> RecurringExpenseCategory:
    return get_object_or_404(RecurringExpenseCategory, pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# RecurringExpense (template)
# ---------------------------------------------------------------------------

def get_all_recurring_expenses(*, search: str = None, category_id: str = None, is_active: str = None) -> QuerySet:
    qs = RecurringExpense.objects.filter(is_deleted=False).select_related("category", "created_by", "updated_by")

    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name"))
    if _clean(category_id):
        qs = qs.filter(category_id=_clean(category_id))
    if _clean(is_active) is not None:
        val = _clean(is_active)
        if val.lower() in ("true", "1"):
            qs = qs.filter(is_active=True)
        elif val.lower() in ("false", "0"):
            qs = qs.filter(is_active=False)

    return qs.order_by("name")


def get_recurring_expense_by_id(pk: int) -> RecurringExpense:
    return get_object_or_404(
        RecurringExpense.objects.select_related("category"), pk=pk, is_deleted=False,
    )


def get_pending_recurring_expenses(*, period: str, category_id: str = None) -> QuerySet:
    """
    Active, non-deleted templates eligible for `period` (period >= start_date)
    that do NOT already have an assignment for it — feeds the Post Dues screen.

    Eligibility is by (year, month) only, matching
    services.create_recurring_expense_assignment exactly — a template
    started on any day of a month is eligible for THAT month, not just
    months starting on or after its exact start_date. Implemented as
    start_date < first day of the FOLLOWING period, which is equivalent to
    "template's start month <= period's month" without day-of-month noise.
    """
    y, m = (int(p) for p in period.split("-"))
    from datetime import date
    next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)
    next_period_start = date(next_y, next_m, 1)

    qs = RecurringExpense.objects.filter(
        is_deleted=False, is_active=True, start_date__lt=next_period_start,
    ).select_related("category")

    if _clean(category_id):
        qs = qs.filter(category_id=_clean(category_id))

    already_assigned_ids = RecurringExpenseAssignment.objects.filter(
        period=period, is_deleted=False,
    ).values_list("recurring_expense_id", flat=True)

    return qs.exclude(id__in=already_assigned_ids).order_by("category__name", "name")


# ---------------------------------------------------------------------------
# RecurringExpenseAssignment
# ---------------------------------------------------------------------------

def get_all_recurring_expense_assignments(
    *,
    recurring_expense_id : str = None,
    period                : str = None,
    category_id           : str = None,
    payment_status        : str = None,
    search                : str = None,
) -> QuerySet:
    qs = RecurringExpenseAssignment.objects.filter(is_deleted=False).select_related(
        "recurring_expense", "category", "assigned_by",
    )

    if _clean(recurring_expense_id):
        qs = qs.filter(recurring_expense_id=_clean(recurring_expense_id))
    if _clean(period):
        qs = qs.filter(period=_clean(period))
    if _clean(category_id):
        qs = qs.filter(category_id=_clean(category_id))
    if _clean(payment_status):
        qs = qs.filter(payment_status=_clean(payment_status))
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name_snapshot"))

    return qs.order_by("-period", "-assigned_at")


def get_recurring_expense_assignment_by_id(pk: int) -> RecurringExpenseAssignment:
    return get_object_or_404(
        RecurringExpenseAssignment.objects.select_related("recurring_expense", "category", "assigned_by"),
        pk=pk, is_deleted=False,
    )


# ---------------------------------------------------------------------------
# RecurringExpenseAssignmentPayment
# ---------------------------------------------------------------------------

def get_all_recurring_expense_payments(
    *, assignment_id: str = None, date_from: str = None, date_to: str = None,
) -> QuerySet:
    # The read serializer outputs only the assignment's ID (no join needed),
    # created_by and updated_by — select exactly those.
    qs = RecurringExpenseAssignmentPayment.objects.filter(is_deleted=False).select_related(
        "created_by", "updated_by",
    )

    if _clean(assignment_id):
        qs = qs.filter(assignment_id=_clean(assignment_id))
    if _clean(date_from):
        qs = qs.filter(payment_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(payment_date__lte=_clean(date_to))

    return qs.order_by("-payment_date", "-created_at")


def get_recurring_expense_payment_by_id(pk: int) -> RecurringExpenseAssignmentPayment:
    return get_object_or_404(RecurringExpenseAssignmentPayment, pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def get_recurring_expense_flow_stats() -> dict:
    flow = RecurringExpenseFlow.get_instance()
    return {
        "total_assigned_amount"           : flow.total_assigned_amount,
        "total_paid_amount"               : flow.total_paid_amount,
        "total_pending_amount"            : flow.total_pending_amount,
        "total_assignments_count"         : flow.total_assignments_count,
        "total_active_templates"          : flow.total_active_templates,
        "total_active_monthly_obligation" : flow.total_active_monthly_obligation,
    }


def get_all_recurring_expense_monthly_stats(*, is_fully_paid: str = None) -> QuerySet:
    qs = RecurringExpenseMonthlyStats.objects.all()
    if _clean(is_fully_paid) is not None:
        val = _clean(is_fully_paid)
        if val.lower() in ("true", "1"):
            qs = qs.filter(is_fully_paid=True)
        elif val.lower() in ("false", "0"):
            qs = qs.filter(is_fully_paid=False)
    return qs.order_by("-period")


def get_recurring_expense_monthly_stats_by_period(period: str) -> dict:
    """
    Read-only — returns zeroed placeholder values if no row exists yet for
    this period (a GET request must never have the side effect of creating
    one; rows are only ever created by an actual assignment/payment).
    """
    row = RecurringExpenseMonthlyStats.objects.filter(period=period).first()
    if row:
        return {
            "period"          : row.period,
            "total_assigned"  : row.total_assigned,
            "total_paid"      : row.total_paid,
            "total_pending"   : row.total_pending,
            "is_fully_paid"   : row.is_fully_paid,
        }
    return {
        "period"          : period,
        "total_assigned"  : 0,
        "total_paid"      : 0,
        "total_pending"   : 0,
        "is_fully_paid"   : False,
    }
