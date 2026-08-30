from decimal import ROUND_DOWN, Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import AccountTransfer, PaymentAllocation, PaymentMethod

# ---------------------------------------------------------------------------
# Phase 1 scope only: create/edit/soft-delete PaymentMethod rows themselves.
# No balance-moving logic here — that's the Phase 2 allocation engine
# (record_allocations/reverse_allocations/refresh_allocations) and the
# Phase 6 transfer service.
# ---------------------------------------------------------------------------


def create_method(*, name: str, account_number: str = "", user) -> PaymentMethod:
    name = name.strip()
    if not name:
        raise ValidationError({"name": "Method name cannot be blank."})
    if PaymentMethod.objects.filter(name__iexact=name).exists():
        raise ValidationError({"name": f"A method named '{name}' already exists."})

    return PaymentMethod.objects.create(
        name=name,
        account_number=account_number,
        created_by=user,
        updated_by=user,
    )


def update_method(
    *, pk: int, name: str = None, account_number: str = None, user,
) -> PaymentMethod:
    method = get_object_or_404(PaymentMethod, pk=pk, is_deleted=False)

    if method.is_protected:
        raise ValidationError({"detail": f"'{method.name}' is a protected method and cannot be edited."})

    if name is not None:
        name = name.strip()
        if not name:
            raise ValidationError({"name": "Method name cannot be blank."})
        if PaymentMethod.objects.filter(name__iexact=name).exclude(pk=method.pk).exists():
            raise ValidationError({"name": f"A method named '{name}' already exists."})
        method.name = name

    if account_number is not None:
        method.account_number = account_number

    method.updated_by = user
    method.save(update_fields=["name", "account_number", "updated_by", "updated_at"])
    return method


def soft_delete_method(*, pk: int, user) -> None:
    method = get_object_or_404(PaymentMethod, pk=pk, is_deleted=False)

    if method.is_protected:
        raise ValidationError({"detail": f"'{method.name}' is a protected method and cannot be deleted."})
    if method.balance != 0:
        raise ValidationError({
            "detail": (
                f"Cannot delete '{method.name}' — it still holds a balance of "
                f"{method.balance}. Move or clear the balance first."
            )
        })

    method.is_deleted = True
    method.deleted_at = timezone.now()
    method.deleted_by = user
    method.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


# ---------------------------------------------------------------------------
# Allocation engine — the ONLY functions allowed to write PaymentAllocation
# rows or adjust PaymentMethod.balance. Mirrors cash_flow.services'
# _adjust_cashflow + record_cash_movement/refresh_cash_movement/
# reverse_cash_movement pattern: `source` is the model instance that caused
# the transaction, (source_model, source_id) derived the same way.
# ---------------------------------------------------------------------------

def _source_label(source) -> str:
    return f"{source._meta.app_label}.{source._meta.model_name}"


def _lock_methods(method_ids):
    """select_for_update, always sorted by pk — every caller locks methods
    in the same order, so two concurrent multi-method transactions can
    never deadlock on each other. Returns {pk: locked PaymentMethod}."""
    locked = PaymentMethod.objects.select_for_update().filter(
        pk__in=method_ids,
    ).order_by("pk")
    return {m.pk: m for m in locked}


@transaction.atomic
def record_allocations(
    source, *, direction: str, splits, total_amount: Decimal, date, user,
) -> list:
    """
    Records how a single inflow/outflow was split across one or more
    payment methods. `splits` is [(payment_method, amount), ...] — resolved
    PaymentMethod instances, not raw ids. Validates the split before
    writing anything; an outflow that would take any method negative is
    rejected in full, with every short method named, not just the first.
    """
    if total_amount is None or total_amount <= 0:
        raise ValidationError({"total_amount": "Total amount must be greater than zero."})
    if not splits:
        raise ValidationError({"splits": "At least one method must be selected."})
    if direction not in (PaymentAllocation.Direction.INFLOW, PaymentAllocation.Direction.OUTFLOW):
        raise ValidationError({"direction": "Must be 'inflow' or 'outflow'."})

    method_ids = [m.pk for m, _ in splits]
    if len(set(method_ids)) != len(method_ids):
        raise ValidationError({"splits": "The same method cannot be selected more than once."})

    for _, amount in splits:
        if amount is None or amount <= 0:
            raise ValidationError({"splits": "Every method's amount must be greater than zero."})

    split_total = sum(amount for _, amount in splits)
    if split_total != total_amount:
        raise ValidationError({
            "splits": f"Split amounts total {split_total}, which doesn't match the transaction amount {total_amount}."
        })

    locked = _lock_methods(method_ids)

    if direction == PaymentAllocation.Direction.OUTFLOW:
        shortfalls = [
            f"{locked[m.pk].name} only has {locked[m.pk].balance}, this outflow needs {amount} from it."
            for m, amount in splits
            if amount > locked[m.pk].balance
        ]
        if shortfalls:
            raise ValidationError({"splits": shortfalls})

    created = []
    for method, amount in splits:
        locked_method = locked[method.pk]
        if direction == PaymentAllocation.Direction.INFLOW:
            locked_method.balance += amount
        else:
            locked_method.balance -= amount
        locked_method.save(update_fields=["balance"])

        created.append(PaymentAllocation.objects.create(
            payment_method=locked_method,
            source_model=_source_label(source),
            source_id=source.pk,
            direction=direction,
            amount=amount,
            date=date,
        ))

    return created


@transaction.atomic
def reverse_allocations(source) -> None:
    """
    Soft-deletes every active allocation for this source and undoes its
    balance effect. No balance-floor check here — reversing a past inflow
    is allowed to take a method negative (the money was already spent
    elsewhere before the entry got deleted; that's honest information, the
    same "don't clamp, don't hide" reasoning cash_flow._adjust_cashflow
    already applies to cash_in_hand). No-op if nothing to reverse.
    """
    allocations = list(PaymentAllocation.objects.filter(
        source_model=_source_label(source), source_id=source.pk, is_deleted=False,
    ))
    if not allocations:
        return

    locked = _lock_methods(sorted({a.payment_method_id for a in allocations}))

    for allocation in allocations:
        method = locked[allocation.payment_method_id]
        if allocation.direction == PaymentAllocation.Direction.INFLOW:
            method.balance -= allocation.amount
        else:
            method.balance += allocation.amount

    for method in locked.values():
        method.save(update_fields=["balance"])

    PaymentAllocation.objects.filter(
        pk__in=[a.pk for a in allocations],
    ).update(is_deleted=True)


@transaction.atomic
def refresh_allocations(
    source, *, direction: str, splits, total_amount: Decimal, date, user,
) -> list:
    """
    For edits that change how a transaction was split (e.g. an advance
    capped at confirmation). Reverses the old split first so the new
    split's balance check runs fairly against money that's already back.
    """
    reverse_allocations(source)
    return record_allocations(
        source, direction=direction, splits=splits, total_amount=total_amount,
        date=date, user=user,
    )


# ---------------------------------------------------------------------------
# Shared helpers for callers (billing/purchases) wiring the engine in
# ---------------------------------------------------------------------------

def derive_legacy_method_label(splits) -> str:
    """
    Fills the old Payment.method/SupplierPayment.method CharField for
    backward compatibility (existing reports/PDFs still read it as a rough
    label) now that a payment can be split across methods. A single-method
    payment shows that method's name; a split shows "multiple" — the real,
    itemized answer lives in the PaymentAllocation rows themselves, shown
    via the `allocations` field on the read serializers.
    """
    if len(splits) == 1:
        return splits[0][0].name.lower()[:100]
    return "multiple"


def prorate_splits(legs, new_total: Decimal):
    """
    Shrinks (or grows) an existing split to a new total, proportionally,
    while keeping the legs summing to EXACTLY new_total to 4 decimal
    places — largest-remainder rounding, not naive per-leg rounding, so
    this can't reproduce the "29,999.996" drift bug class. `legs` is
    [(payment_method, amount), ...] from the CURRENT allocations; returns
    the same shape scaled to new_total. Empty legs or a zero old total
    return [] (nothing to prorate).
    """
    old_total = sum(amount for _, amount in legs)
    if not legs or old_total <= 0 or new_total <= 0:
        return []

    step = Decimal("0.0001")
    scaled = [
        (method, (amount * new_total / old_total).quantize(step, rounding=ROUND_DOWN))
        for method, amount in legs
    ]
    shortfall = new_total - sum(amount for _, amount in scaled)
    shortfall_units = int((shortfall / step).to_integral_value())

    # Distribute the rounding-down shortfall one step at a time to the legs
    # with the largest truncated remainder first (largest-remainder method).
    remainders = sorted(
        range(len(legs)),
        key=lambda i: (legs[i][1] * new_total / old_total) - scaled[i][1],
        reverse=True,
    )
    result = [[method, amount] for method, amount in scaled]
    for i in range(shortfall_units):
        result[remainders[i % len(remainders)]][1] += step

    return [(method, amount) for method, amount in result]


# ---------------------------------------------------------------------------
# Phase 6 — Transfers. Moves balance directly between two methods; never
# touches cash_in_hand (no sync_*/record_cash_movement call anywhere below
# — no real cash enters or leaves the business, only which account holds
# it changes). Reuses the Phase 2 engine's own locking/validation/
# insufficient-balance rejection instead of a second balance-moving path.
# ---------------------------------------------------------------------------

@transaction.atomic
def transfer_between_methods(
    *, from_method_id: int, to_method_id: int, amount: Decimal, date, note: str = "", user,
) -> AccountTransfer:
    """
    Records a transfer and moves balance from from_method to to_method.
    Implemented as two record_allocations calls against the SAME
    AccountTransfer row as source (one outflow leg, one inflow leg) — the
    balance check on the outflow leg is the Phase 2 engine's own, not
    reimplemented here.

    Pre-locks BOTH methods together, sorted by pk, before either
    record_allocations call. Without this, each call would lock only its
    own method in isolation, and two concurrent transfers running in
    OPPOSITE directions between the same two methods (A→B and B→A) would
    lock in opposite orders and deadlock. Locking both up front — in the
    same global order every transfer uses — makes the two inner locks
    no-ops (already held by this transaction) and rules that out.
    """
    if from_method_id == to_method_id:
        raise ValidationError({"to_method": "Cannot transfer a method to itself."})
    if amount is None or amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})

    from_method = get_object_or_404(PaymentMethod, pk=from_method_id, is_deleted=False)
    to_method   = get_object_or_404(PaymentMethod, pk=to_method_id, is_deleted=False)

    _lock_methods(sorted([from_method_id, to_method_id]))

    transfer = AccountTransfer.objects.create(
        from_method=from_method, to_method=to_method, amount=amount,
        date=date, note=note, created_by=user, updated_by=user,
    )

    record_allocations(
        transfer, direction="outflow", splits=[(from_method, amount)],
        total_amount=amount, date=date, user=user,
    )
    record_allocations(
        transfer, direction="inflow", splits=[(to_method, amount)],
        total_amount=amount, date=date, user=user,
    )

    return transfer


@transaction.atomic
def delete_account_transfer(*, pk: int, user) -> None:
    """Soft-deletes a transfer and reverses both legs' balance effect —
    reverse_allocations already finds both (same source, one per method)
    and locks/reverses them together, so no new reversal logic is needed."""
    transfer = get_object_or_404(AccountTransfer, pk=pk, is_deleted=False)

    transfer.is_deleted = True
    transfer.deleted_at = timezone.now()
    transfer.deleted_by = user
    transfer.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    reverse_allocations(transfer)
