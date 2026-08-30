from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    RecurringExpense, RecurringExpenseAssignment, RecurringExpenseAssignmentPayment,
    RecurringExpenseCategory, RecurringExpenseFlow, RecurringExpenseMonthlyStats,
)


def _period_tuple(period: str) -> tuple:
    y, m = period.split("-")
    return int(y), int(m)


def _compute_payment_status(amount: Decimal, amount_paid: Decimal) -> str:
    if amount_paid <= 0:
        return RecurringExpenseAssignment.PaymentStatus.UNPAID
    if amount_paid >= amount:
        return RecurringExpenseAssignment.PaymentStatus.PAID
    return RecurringExpenseAssignment.PaymentStatus.PARTIAL


# ---------------------------------------------------------------------------
# Internal atomic singleton adjusters — NEVER call from outside this module
# ---------------------------------------------------------------------------

def _adjust_recurring_expense_flow(
    *,
    total_assigned_amount_delta       : Decimal = Decimal("0"),
    total_paid_amount_delta           : Decimal = Decimal("0"),
    total_assignments_count_delta     : int = 0,
    total_active_templates_delta      : int = 0,
    total_active_monthly_obligation_delta : Decimal = Decimal("0"),
    user,
) -> RecurringExpenseFlow:
    """
    Atomically adjusts the RecurringExpenseFlow singleton, then recalculates
    and SAVES total_pending_amount so nothing downstream ever has to sum rows
    at request time. This is the ONLY function that writes to RecurringExpenseFlow.
    """
    with transaction.atomic():
        flow = RecurringExpenseFlow.objects.select_for_update().get_or_create(pk=1)[0]

        flow.total_assigned_amount = max(Decimal("0"), flow.total_assigned_amount + total_assigned_amount_delta)
        flow.total_paid_amount     = max(Decimal("0"), flow.total_paid_amount + total_paid_amount_delta)
        flow.total_assignments_count = max(0, flow.total_assignments_count + total_assignments_count_delta)
        flow.total_active_templates  = max(0, flow.total_active_templates + total_active_templates_delta)
        flow.total_active_monthly_obligation = max(
            Decimal("0"), flow.total_active_monthly_obligation + total_active_monthly_obligation_delta
        )

        flow.total_pending_amount = max(Decimal("0"), flow.total_assigned_amount - flow.total_paid_amount)

        flow.last_updated_by = user
        flow.save()
        return flow


def _adjust_recurring_expense_monthly_stats(
    *,
    period: str,
    total_assigned_delta : Decimal = Decimal("0"),
    total_paid_delta     : Decimal = Decimal("0"),
) -> RecurringExpenseMonthlyStats:
    """
    Atomically adjusts the one RecurringExpenseMonthlyStats row for `period`,
    creating it if this is the first assignment/payment ever recorded for
    that month. The ONLY function that writes to RecurringExpenseMonthlyStats.
    """
    with transaction.atomic():
        stats, _ = RecurringExpenseMonthlyStats.objects.select_for_update().get_or_create(period=period)

        stats.total_assigned = max(Decimal("0"), stats.total_assigned + total_assigned_delta)
        stats.total_paid     = max(Decimal("0"), stats.total_paid + total_paid_delta)
        stats.total_pending  = max(Decimal("0"), stats.total_assigned - stats.total_paid)
        stats.is_fully_paid  = stats.total_assigned > 0 and stats.total_pending == 0

        stats.save()
        return stats


# ---------------------------------------------------------------------------
# RecurringExpenseCategory services
# ---------------------------------------------------------------------------

def create_recurring_expense_category(*, name: str, description: str = "", user) -> RecurringExpenseCategory:
    from rest_framework.exceptions import ValidationError

    if not name.strip():
        raise ValidationError({"name": "Category name cannot be blank."})

    return RecurringExpenseCategory.objects.create(
        name=name.strip(), description=description, created_by=user,
    )


def update_recurring_expense_category(*, pk: int, name: str = None, description: str = None, user) -> RecurringExpenseCategory:
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    category = get_object_or_404(RecurringExpenseCategory, pk=pk, is_deleted=False)

    if name is not None:
        if not name.strip():
            raise ValidationError({"name": "Category name cannot be blank."})
        category.name = name.strip()
    if description is not None:
        category.description = description

    category.save(update_fields=["name", "description"])
    return category


def delete_recurring_expense_category(*, pk: int, user) -> None:
    """
    Soft-deletes a category — only hides it from active use (dropdowns/new
    assignments). Every past RecurringExpenseAssignment already snapshotted
    its own category_name_snapshot, so history is completely unaffected.
    """
    from django.shortcuts import get_object_or_404

    category = get_object_or_404(RecurringExpenseCategory, pk=pk, is_deleted=False)
    category.is_deleted = True
    category.deleted_at = timezone.now()
    category.deleted_by = user
    category.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


# ---------------------------------------------------------------------------
# RecurringExpense (template) services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_recurring_expense(
    *, name: str, category_id: int, amount: Decimal, start_date, note: str = "", user,
) -> RecurringExpense:
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    if not name.strip():
        raise ValidationError({"name": "Name cannot be blank."})
    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})

    category = get_object_or_404(RecurringExpenseCategory, pk=category_id, is_deleted=False)

    template = RecurringExpense.objects.create(
        name=name.strip(), category=category, amount=amount,
        start_date=start_date, note=note, created_by=user, updated_by=user,
    )

    # New templates are always active — bump the active-obligation totals.
    _adjust_recurring_expense_flow(
        total_active_templates_delta=+1,
        total_active_monthly_obligation_delta=+amount,
        user=user,
    )

    return template


@transaction.atomic
def update_recurring_expense(
    *, pk: int, name: str = None, category_id: int = None, amount: Decimal = None,
    start_date=None, is_active: bool = None, note: str = None, user,
) -> RecurringExpense:
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    template = get_object_or_404(RecurringExpense, pk=pk, is_deleted=False)

    old_active = template.is_active
    old_amount = template.amount

    if name is not None:
        if not name.strip():
            raise ValidationError({"name": "Name cannot be blank."})
        template.name = name.strip()
    if category_id is not None:
        template.category = get_object_or_404(RecurringExpenseCategory, pk=category_id, is_deleted=False)
    if amount is not None:
        if amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})
        template.amount = amount
    if start_date is not None:
        template.start_date = start_date
    if is_active is not None:
        template.is_active = is_active
    if note is not None:
        template.note = note

    template.updated_by = user
    template.save(update_fields=["name", "category", "amount", "start_date", "is_active", "note", "updated_by", "updated_at"])

    new_active = template.is_active
    new_amount = template.amount

    templates_delta  = 0
    obligation_delta = Decimal("0")
    if old_active and not new_active:
        templates_delta  = -1
        obligation_delta = -old_amount
    elif not old_active and new_active:
        templates_delta  = +1
        obligation_delta = +new_amount
    elif old_active and new_active and old_amount != new_amount:
        obligation_delta = new_amount - old_amount

    if templates_delta or obligation_delta:
        _adjust_recurring_expense_flow(
            total_active_templates_delta=templates_delta,
            total_active_monthly_obligation_delta=obligation_delta,
            user=user,
        )

    return template


@transaction.atomic
def delete_recurring_expense(*, pk: int, user) -> None:
    """Soft-deletes a template. Past assignments/payments are untouched."""
    from django.shortcuts import get_object_or_404

    template = get_object_or_404(RecurringExpense, pk=pk, is_deleted=False)
    was_active = template.is_active
    amount = template.amount

    template.is_deleted = True
    template.deleted_at = timezone.now()
    template.deleted_by = user
    template.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    if was_active:
        _adjust_recurring_expense_flow(
            total_active_templates_delta=-1,
            total_active_monthly_obligation_delta=-amount,
            user=user,
        )


# ---------------------------------------------------------------------------
# RecurringExpenseAssignment services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_recurring_expense_assignment(*, recurring_expense_id: int, period: str, user) -> RecurringExpenseAssignment:
    """
    "Assigns" one template's amount as due for `period`. Never touches cash —
    only a payment does. Snapshots name/category/amount so later template
    edits never rewrite this assignment. Blocked permanently if this template
    already has an assignment for this period (unique constraint + explicit
    pre-check for a clean error message).
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    template = get_object_or_404(
        RecurringExpense.objects.select_for_update(), pk=recurring_expense_id, is_deleted=False,
    )

    if not template.is_active:
        raise ValidationError({"recurring_expense": f"'{template.name}' is inactive and cannot be assigned."})

    try:
        py, pm = _period_tuple(period)
    except (ValueError, AttributeError):
        raise ValidationError({"period": "Must be in YYYY-MM format."})

    sy, sm = template.start_date.year, template.start_date.month
    if (py, pm) < (sy, sm):
        raise ValidationError({"period": f"'{template.name}' isn't eligible until {sy:04d}-{sm:02d}."})

    if RecurringExpenseAssignment.objects.filter(
        recurring_expense=template, period=period, is_deleted=False,
    ).exists():
        raise ValidationError({"period": f"'{template.name}' has already been assigned for {period}."})

    assignment = RecurringExpenseAssignment.objects.create(
        recurring_expense=template,
        period=period,
        name_snapshot=template.name,
        category=template.category,
        category_name_snapshot=template.category.name,
        amount=template.amount,
        assigned_by=user,
    )

    _adjust_recurring_expense_flow(
        total_assigned_amount_delta=+template.amount,
        total_assignments_count_delta=+1,
        user=user,
    )
    _adjust_recurring_expense_monthly_stats(period=period, total_assigned_delta=+template.amount)

    return assignment


@transaction.atomic
def delete_recurring_expense_assignment(*, pk: int, user) -> None:
    """
    Soft-deletes a mistakenly-posted assignment — ONLY allowed while it's
    still fully unpaid (amount_paid == 0). Reverses it out of
    RecurringExpenseFlow and that period's RecurringExpenseMonthlyStats.
    If any payment has been recorded, this is rejected — delete the
    payment(s) first via delete_recurring_expense_payment, which is the only
    thing allowed to move amount_paid back down to zero.
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    assignment = get_object_or_404(
        RecurringExpenseAssignment.objects.select_for_update(), pk=pk, is_deleted=False,
    )

    if assignment.amount_paid > 0:
        raise ValidationError({
            "detail": "This assignment has payments recorded against it and can no longer be "
                      "unassigned. Delete the payment(s) first, then unassign it."
        })

    assignment.is_deleted = True
    assignment.deleted_at = timezone.now()
    assignment.deleted_by = user
    assignment.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    _adjust_recurring_expense_flow(
        total_assigned_amount_delta=-assignment.amount,
        total_assignments_count_delta=-1,
        user=user,
    )
    _adjust_recurring_expense_monthly_stats(period=assignment.period, total_assigned_delta=-assignment.amount)


def bulk_create_recurring_expense_assignments(*, period: str, category_id: int = None, user) -> dict:
    """
    Assigns every active, not-yet-assigned-for-`period` template, optionally
    scoped to one category. Each assignment is attempted independently — one
    failure never blocks the rest (these are independent obligations).
    """
    from .selectors import get_pending_recurring_expenses

    pending = get_pending_recurring_expenses(period=period, category_id=category_id)

    created = []
    failed  = []
    for template in pending:
        try:
            assignment = create_recurring_expense_assignment(
                recurring_expense_id=template.id, period=period, user=user,
            )
            created.append(assignment)
        except Exception as exc:
            failed.append({"recurring_expense_id": template.id, "name": template.name, "error": str(exc)})

    return {"created": created, "failed": failed}


# ---------------------------------------------------------------------------
# RecurringExpenseAssignmentPayment services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_recurring_expense_payment(
    *, assignment_id: int, amount: Decimal, payment_date, method_allocations: list, note: str = "", user,
) -> RecurringExpenseAssignmentPayment:
    """
    Records a payment against an assignment — the ONLY moment cash actually
    leaves the business for a recurring expense. Rejected if it would exceed
    the assignment's remaining outstanding balance (mirrors
    purchases.create_supplier_payment's overpayment guard exactly).
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected."})

    assignment = get_object_or_404(
        RecurringExpenseAssignment.objects.select_for_update(), pk=assignment_id,
    )

    outstanding = assignment.amount - assignment.amount_paid
    if amount > outstanding:
        raise ValidationError({
            "amount": f"Payment of {amount} exceeds outstanding balance. Outstanding: {outstanding}."
        })

    payment = RecurringExpenseAssignmentPayment.objects.create(
        assignment=assignment, amount=amount, payment_date=payment_date,
        note=note, created_by=user, updated_by=user,
    )

    assignment.amount_paid += amount
    assignment.payment_status = _compute_payment_status(assignment.amount, assignment.amount_paid)
    assignment.save(update_fields=["amount_paid", "payment_status"])

    _adjust_recurring_expense_flow(total_paid_amount_delta=+amount, user=user)
    _adjust_recurring_expense_monthly_stats(period=assignment.period, total_paid_delta=+amount)

    from cash_flow.services import record_cash_movement, sync_recurring_expense_payment_made
    sync_recurring_expense_payment_made(amount=amount, user=user)
    record_cash_movement(payment)

    from payment_methods.services import record_allocations
    record_allocations(
        payment, direction="outflow", splits=method_allocations,
        total_amount=amount, date=payment_date, user=user,
    )

    return payment


@transaction.atomic
def delete_recurring_expense_payment(*, pk: int, user) -> None:
    """
    Soft-deletes a payment and reverses ALL FOUR synced places at once —
    the assignment's own amount_paid/payment_status, RecurringExpenseFlow,
    that period's RecurringExpenseMonthlyStats, and CashFlow.cash_in_hand.
    Every reversal caller routes through this one function so nothing can
    drift out of sync.
    """
    from django.shortcuts import get_object_or_404

    payment = get_object_or_404(RecurringExpenseAssignmentPayment, pk=pk, is_deleted=False)
    assignment = get_object_or_404(
        RecurringExpenseAssignment.objects.select_for_update(), pk=payment.assignment_id,
    )
    amount = payment.amount

    payment.is_deleted = True
    payment.deleted_at = timezone.now()
    payment.deleted_by = user
    payment.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    assignment.amount_paid = max(Decimal("0"), assignment.amount_paid - amount)
    assignment.payment_status = _compute_payment_status(assignment.amount, assignment.amount_paid)
    assignment.save(update_fields=["amount_paid", "payment_status"])

    _adjust_recurring_expense_flow(total_paid_amount_delta=-amount, user=user)
    _adjust_recurring_expense_monthly_stats(period=assignment.period, total_paid_delta=-amount)

    from cash_flow.services import reverse_cash_movement, sync_recurring_expense_payment_deleted
    sync_recurring_expense_payment_deleted(amount=amount, user=user)
    reverse_cash_movement(payment)

    from payment_methods.services import reverse_allocations
    reverse_allocations(payment)
