from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    CashAdjustment, CashManagementFlow, Investor, InvestorTransaction,
    InvestorValuationEntry, OwnerTransaction,
)


def _add_months(year: int, month: int, delta: int) -> tuple:
    """Month-only arithmetic, no external date libraries needed. Mirrors
    assets.services._add_months / cash_flow.selectors._add_months exactly."""
    total = (year * 12 + (month - 1)) + delta
    return total // 12, (total % 12) + 1


# ---------------------------------------------------------------------------
# Internal atomic CashManagementFlow adjuster — NEVER call from outside this module
# ---------------------------------------------------------------------------

def _adjust_cash_management_flow(
    *,
    total_cash_lost_delta               : Decimal = Decimal("0"),
    total_cash_recovered_delta          : Decimal = Decimal("0"),
    total_investor_capital_delta        : Decimal = Decimal("0"),
    total_investor_withdrawn_delta      : Decimal = Decimal("0"),
    total_investor_net_worth_delta      : Decimal = Decimal("0"),
    total_owner_contributions_delta       : Decimal = Decimal("0"),
    total_owner_drawings_delta            : Decimal = Decimal("0"),
    total_owner_contributions_count_delta : int = 0,
    total_owner_withdrawals_count_delta   : int = 0,
    user,
) -> CashManagementFlow:
    """
    Atomically adjusts the CashManagementFlow singleton by the given deltas,
    then recalculates and SAVES the derived fields (net_cash_lost,
    net_investor_capital, net_owner_capital) so nothing downstream ever has
    to sum rows at request time. Positive delta = increase. Negative delta =
    decrease. This is the ONLY function that writes to CashManagementFlow.
    """
    with transaction.atomic():
        cmf = CashManagementFlow.objects.select_for_update().get_or_create(pk=1)[0]

        cmf.total_cash_lost = max(
            Decimal("0"), cmf.total_cash_lost + total_cash_lost_delta
        )
        cmf.total_cash_recovered = max(
            Decimal("0"), cmf.total_cash_recovered + total_cash_recovered_delta
        )
        cmf.total_investor_capital = max(
            Decimal("0"), cmf.total_investor_capital + total_investor_capital_delta
        )
        cmf.total_investor_withdrawn = max(
            Decimal("0"), cmf.total_investor_withdrawn + total_investor_withdrawn_delta
        )
        cmf.total_investor_net_worth = max(
            Decimal("0"), cmf.total_investor_net_worth + total_investor_net_worth_delta
        )
        cmf.total_owner_contributions = max(
            Decimal("0"), cmf.total_owner_contributions + total_owner_contributions_delta
        )
        cmf.total_owner_drawings = max(
            Decimal("0"), cmf.total_owner_drawings + total_owner_drawings_delta
        )
        cmf.total_owner_contributions_count = max(
            0, cmf.total_owner_contributions_count + total_owner_contributions_count_delta
        )
        cmf.total_owner_withdrawals_count = max(
            0, cmf.total_owner_withdrawals_count + total_owner_withdrawals_count_delta
        )

        # Derived fields — recomputed and stored on every sync, not on read.
        cmf.net_cash_lost = max(
            Decimal("0"), cmf.total_cash_lost - cmf.total_cash_recovered
        )
        cmf.net_investor_capital = cmf.total_investor_capital - cmf.total_investor_withdrawn
        # NOT floored — a sole owner can draw out more than they've deposited.
        cmf.net_owner_capital = cmf.total_owner_contributions - cmf.total_owner_drawings

        cmf.last_updated_by = user
        cmf.save()
        return cmf


# ---------------------------------------------------------------------------
# Catch-up investor growth — the core "no cron" mechanism, mirrors
# assets.services._catch_up_asset_depreciation but growing instead of
# shrinking, and compounding on current_worth directly (no fixed-cost-year
# blocks needed since investor principal can change any time).
# ---------------------------------------------------------------------------

def _catch_up_investor_growth(investor: Investor, user=None) -> None:
    """
    Posts any InvestorValuationEntry rows that should already exist for this
    investor, up to and including the current month — compound monthly
    growth: current_worth += current_worth * (growth_rate / 12) each
    elapsed month, using whatever growth_rate is active at the moment each
    month gets posted (rate changes only affect entries posted after the
    change; already-posted history is immune). No-op if growth_rate is 0.
    """
    rate = investor.growth_rate
    if rate <= 0:
        return

    today = timezone.localdate()
    current_month_start = date(today.year, today.month, 1)

    last_entry = InvestorValuationEntry.objects.filter(
        investor=investor,
    ).order_by("-period").first()

    if last_entry:
        ly, lm = (int(p) for p in last_entry.period.split("-"))
        ny, nm = _add_months(ly, lm, 1)
    else:
        created_date = timezone.localtime(investor.created_at).date()
        ny, nm = _add_months(created_date.year, created_date.month, 1)

    next_date = date(ny, nm, 1)
    precision = Decimal("0.0001")

    while next_date <= current_month_start:
        monthly_growth = (investor.current_worth * rate / Decimal("12")).quantize(
            precision, rounding=ROUND_HALF_UP
        )

        worth_before = investor.current_worth
        worth_after = worth_before + monthly_growth
        period_str = f"{next_date.year:04d}-{next_date.month:02d}"

        try:
            # Savepoint so a unique-constraint hit doesn't poison an outer
            # transaction (catch-up runs inside atomic services too).
            with transaction.atomic():
                InvestorValuationEntry.objects.create(
                    investor=investor,
                    period=period_str,
                    rate_applied=rate,
                    worth_before=worth_before,
                    worth_after=worth_after,
                    amount=monthly_growth,
                    note="Auto-posted monthly growth (catch-up)",
                    created_by=user,
                )
        except IntegrityError:
            # uniq_investor_valuation_period: a concurrent catch-up already
            # posted this month (and everything after it) — pick up its
            # result and stop instead of double-compounding.
            investor.refresh_from_db(fields=["current_worth"])
            return

        investor.current_worth = worth_after
        investor.save(update_fields=["current_worth"])

        _adjust_cash_management_flow(
            total_investor_net_worth_delta=+monthly_growth,
            user=user,
        )

        ny2, nm2 = _add_months(next_date.year, next_date.month, 1)
        next_date = date(ny2, nm2, 1)


def catch_up_all_investor_growth(user=None) -> None:
    """
    Runs growth catch-up for every active investor, gated by an O(1) month
    marker on the flow singleton: growth only ever becomes due at a month
    boundary (a new investor's first entry is due the FOLLOWING month, and
    rate edits only affect future postings), so once everyone is posted
    through the current month there is nothing to check until the 1st of the
    next month. Selectors call this on every stats/investor-list read —
    previously that meant one "latest entry" query per growth investor per
    request; now it's a free field comparison on the already-fetched
    singleton, with the real per-investor sweep running once per month.
    Posting logic and numbers are completely unchanged.
    """
    today = timezone.localdate()
    current_period = f"{today.year:04d}-{today.month:02d}"

    cmf = CashManagementFlow.get_instance()
    if cmf.growth_caught_up_through == current_period:
        return

    for investor in Investor.objects.filter(is_deleted=False):
        _catch_up_investor_growth(investor, user=user)

    # update() — not save() — so the marker stamp doesn't touch last_updated_at.
    CashManagementFlow.objects.filter(pk=1).update(growth_caught_up_through=current_period)


# ---------------------------------------------------------------------------
# CashAdjustment services (lost/found cash)
# ---------------------------------------------------------------------------

@transaction.atomic
def create_cash_adjustment(
    *, amount: Decimal, adjustment_type: str, adjustment_date, method_allocations: list,
    reason: str = "", user,
) -> CashAdjustment:
    """
    Records a lost or found cash adjustment. Lost deducts from
    CashFlow.cash_in_hand, found adds to it. Independent entries — a found
    entry is never linked to or capped by a specific prior lost entry.
    """
    from rest_framework.exceptions import ValidationError

    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if adjustment_type not in (CashAdjustment.AdjustmentType.LOST, CashAdjustment.AdjustmentType.FOUND):
        raise ValidationError({"adjustment_type": "Must be 'lost' or 'found'."})
    if not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected."})

    adjustment = CashAdjustment.objects.create(
        amount=amount,
        adjustment_type=adjustment_type,
        adjustment_date=adjustment_date,
        reason=reason,
        created_by=user,
        updated_by=user,
    )

    from cash_flow.services import record_cash_movement, sync_cash_found, sync_cash_lost
    from payment_methods.services import record_allocations

    is_lost = adjustment_type == CashAdjustment.AdjustmentType.LOST
    if is_lost:
        _adjust_cash_management_flow(total_cash_lost_delta=+amount, user=user)
        sync_cash_lost(amount=amount, user=user)
    else:
        _adjust_cash_management_flow(total_cash_recovered_delta=+amount, user=user)
        sync_cash_found(amount=amount, user=user)

    record_cash_movement(adjustment)
    record_allocations(
        adjustment, direction="outflow" if is_lost else "inflow", splits=method_allocations,
        total_amount=amount, date=adjustment_date, user=user,
    )
    return adjustment


@transaction.atomic
def delete_cash_adjustment(*, pk: int, user) -> None:
    """Soft-deletes a cash adjustment and reverses its cash_in_hand effect."""
    from django.shortcuts import get_object_or_404

    adjustment = get_object_or_404(CashAdjustment, pk=pk, is_deleted=False)
    amount     = adjustment.amount

    adjustment.is_deleted = True
    adjustment.deleted_at = timezone.now()
    adjustment.deleted_by = user
    adjustment.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    from cash_flow.services import reverse_cash_movement, sync_cash_found, sync_cash_lost

    if adjustment.adjustment_type == CashAdjustment.AdjustmentType.LOST:
        _adjust_cash_management_flow(total_cash_lost_delta=-amount, user=user)
        sync_cash_found(amount=amount, user=user)  # reverse: restore cash_in_hand
    else:
        _adjust_cash_management_flow(total_cash_recovered_delta=-amount, user=user)
        sync_cash_lost(amount=amount, user=user)  # reverse: remove cash_in_hand again

    reverse_cash_movement(adjustment)

    from payment_methods.services import reverse_allocations
    reverse_allocations(adjustment)


# ---------------------------------------------------------------------------
# Investor services
# ---------------------------------------------------------------------------

def create_investor(
    *, name: str, contact_number: str = "", email: str = "", note: str = "",
    growth_rate: Decimal = Decimal("0"), user,
) -> Investor:
    from rest_framework.exceptions import ValidationError

    if not name.strip():
        raise ValidationError({"name": "Investor name cannot be blank."})
    if growth_rate < 0:
        raise ValidationError({"growth_rate": "Growth rate cannot be negative."})

    return Investor.objects.create(
        name=name.strip(),
        contact_number=contact_number,
        email=email,
        note=note,
        growth_rate=growth_rate,
        created_by=user,
        updated_by=user,
    )


def update_investor(
    *, pk: int, name: str = None, contact_number: str = None,
    email: str = None, note: str = None, growth_rate: Decimal = None, user,
) -> Investor:
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    investor = get_object_or_404(Investor, pk=pk, is_deleted=False)

    rate_changed = False
    if name is not None:
        if not name.strip():
            raise ValidationError({"name": "Investor name cannot be blank."})
        investor.name = name.strip()
    if contact_number is not None:
        investor.contact_number = contact_number
    if email is not None:
        investor.email = email
    if note is not None:
        investor.note = note
    if growth_rate is not None:
        if growth_rate < 0:
            raise ValidationError({"growth_rate": "Growth rate cannot be negative."})
        rate_changed = investor.growth_rate != growth_rate
        investor.growth_rate = growth_rate

    investor.updated_by = user
    investor.save(update_fields=["name", "contact_number", "email", "note", "growth_rate", "updated_by", "updated_at"])

    if rate_changed:
        # Reset the month marker so the next read re-runs the catch-up sweep
        # with the NEW rate — preserves the pre-marker timing exactly (a rate
        # edit takes effect on the next read, never delayed to month-end;
        # already-posted months are immune via their rate_applied snapshot).
        CashManagementFlow.objects.filter(pk=1).update(growth_caught_up_through="")

    return investor


@transaction.atomic
def delete_investor(*, pk: int, user) -> None:
    """
    Soft-deletes an investor. Blocked if they have any non-deleted
    transactions — deleting the investor would orphan real financial
    history; delete/reverse the transactions first if that's truly intended.
    select_for_update: transaction creation locks this same row, so the
    delete waits for any in-flight transaction and re-checks — the
    "no transactions" guard can't be raced past.
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    investor = get_object_or_404(Investor.objects.select_for_update(), pk=pk, is_deleted=False)

    if investor.transactions.filter(is_deleted=False).exists():
        raise ValidationError({
            "detail": "Cannot delete an investor with recorded transactions. Delete their transactions first."
        })

    investor.is_deleted = True
    investor.deleted_at = timezone.now()
    investor.deleted_by = user
    investor.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


# ---------------------------------------------------------------------------
# InvestorTransaction services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_investor_transaction(
    *, investor_id: int, transaction_type: str, amount: Decimal,
    transaction_date, method_allocations: list = None, note: str = "",
    user, is_data_entry: bool = False,
) -> InvestorTransaction:
    """
    Records an investment or withdrawal for an investor. Investment adds to
    CashFlow.cash_in_hand and the investor's net_stake; withdrawal deducts
    from both. A withdrawal is rejected if it would exceed the investor's
    current net_stake — NEVER current_worth (see Investor docstring).

    current_worth moves alongside net_stake: +amount on investment, -amount
    on a normal withdrawal. If a withdrawal brings net_stake to exactly 0
    (full exit), current_worth is forced to exactly 0 too — wiping any
    residual theoretical growth, not just the withdrawn amount. The exact
    change is stored on the transaction as worth_delta so deletion can
    reverse it precisely either way.

    is_data_entry=True (only ever set by data_entry.services, for capital an
    investor put in before this system existed): still updates the
    investor's own totals and CashManagementFlow exactly like a real
    transaction, but skips the CashFlow.cash_in_hand sync — the cash isn't
    actually sitting in the till, so it must not be counted as an inflow.
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if transaction_type not in (InvestorTransaction.TransactionType.INVESTMENT, InvestorTransaction.TransactionType.WITHDRAWAL):
        raise ValidationError({"transaction_type": "Must be 'investment' or 'withdrawal'."})
    # is_data_entry never touches cash_in_hand (see docstring) — no real
    # cash movement to allocate, so no method is required for it.
    if not is_data_entry and not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected."})

    investor = get_object_or_404(Investor.objects.select_for_update(), pk=investor_id, is_deleted=False)

    if transaction_type == InvestorTransaction.TransactionType.WITHDRAWAL and amount > investor.net_stake:
        raise ValidationError({
            "amount": (
                f"Cannot withdraw {amount} — {investor.name} only has "
                f"{investor.net_stake} currently invested."
            )
        })

    # Bring current_worth up to date BEFORE applying this transaction.
    _catch_up_investor_growth(investor, user=user)

    from cash_flow.services import sync_investor_investment, sync_investor_withdrawal

    if transaction_type == InvestorTransaction.TransactionType.INVESTMENT:
        worth_delta = amount
        investor.total_invested += amount
        investor.net_stake      += amount
        investor.current_worth  += worth_delta
        investor.save(update_fields=["total_invested", "net_stake", "current_worth"])

        _adjust_cash_management_flow(
            total_investor_capital_delta=+amount,
            total_investor_net_worth_delta=+worth_delta,
            user=user,
        )
        if not is_data_entry:
            sync_investor_investment(amount=amount, user=user)
    else:
        investor.total_withdrawn += amount
        investor.net_stake       -= amount

        if investor.net_stake == 0:
            # Full exit — wipe any residual theoretical growth, not just the withdrawn amount.
            worth_delta = -investor.current_worth
            investor.current_worth = Decimal("0")
        else:
            worth_delta = -amount
            investor.current_worth += worth_delta

        investor.save(update_fields=["total_withdrawn", "net_stake", "current_worth"])

        _adjust_cash_management_flow(
            total_investor_withdrawn_delta=+amount,
            total_investor_net_worth_delta=+worth_delta,
            user=user,
        )
        if not is_data_entry:
            sync_investor_withdrawal(amount=amount, user=user)

    txn = InvestorTransaction.objects.create(
        investor=investor,
        transaction_type=transaction_type,
        amount=amount,
        worth_delta=worth_delta,
        transaction_date=transaction_date,
        note=note,
        is_data_entry=is_data_entry,
        created_by=user,
        updated_by=user,
    )

    # Recorded even for is_data_entry rows — the drawer has always itemised
    # every non-deleted investor transaction, including opening investments
    # that never moved cash_in_hand (pre-existing behavior, preserved).
    from cash_flow.services import record_cash_movement
    record_cash_movement(txn)

    if not is_data_entry:
        from payment_methods.services import record_allocations
        record_allocations(
            txn,
            direction="inflow" if transaction_type == InvestorTransaction.TransactionType.INVESTMENT else "outflow",
            splits=method_allocations, total_amount=amount, date=transaction_date, user=user,
        )

    return txn


@transaction.atomic
def delete_investor_transaction(*, pk: int, user) -> None:
    """
    Soft-deletes an investor transaction and reverses its effects on the
    investor's balance, current_worth, CashManagementFlow, and cash_in_hand.
    Deleting an investment is rejected if it would push the investor's
    net_stake negative (i.e. a later withdrawal already relied on this
    investment). current_worth is reversed using the transaction's own
    stored worth_delta — exact in every case, including a full-exit
    withdrawal that had wiped residual growth.
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    txn = get_object_or_404(InvestorTransaction, pk=pk, is_deleted=False)
    investor = get_object_or_404(Investor.objects.select_for_update(), pk=txn.investor_id)
    amount = txn.amount

    from cash_flow.services import sync_investor_investment, sync_investor_withdrawal

    if txn.transaction_type == InvestorTransaction.TransactionType.INVESTMENT:
        if investor.net_stake - amount < 0:
            raise ValidationError({
                "detail": (
                    f"Cannot delete this investment — {investor.name}'s net stake would go "
                    f"negative (a later withdrawal already relies on this money)."
                )
            })
        investor.total_invested -= amount
        investor.net_stake      -= amount
        investor.current_worth  -= txn.worth_delta
        investor.save(update_fields=["total_invested", "net_stake", "current_worth"])
        _adjust_cash_management_flow(
            total_investor_capital_delta=-amount,
            total_investor_net_worth_delta=-txn.worth_delta,
            user=user,
        )
        if not txn.is_data_entry:
            sync_investor_withdrawal(amount=amount, user=user)  # reverse: remove cash_in_hand again
    else:
        investor.total_withdrawn -= amount
        investor.net_stake       += amount
        investor.current_worth   -= txn.worth_delta
        investor.save(update_fields=["total_withdrawn", "net_stake", "current_worth"])
        _adjust_cash_management_flow(
            total_investor_withdrawn_delta=-amount,
            total_investor_net_worth_delta=-txn.worth_delta,
            user=user,
        )
        if not txn.is_data_entry:
            sync_investor_investment(amount=amount, user=user)  # reverse: restore cash_in_hand

    txn.is_deleted = True
    txn.deleted_at = timezone.now()
    txn.deleted_by = user
    txn.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    from cash_flow.services import reverse_cash_movement
    reverse_cash_movement(txn)

    if not txn.is_data_entry:
        from payment_methods.services import reverse_allocations
        reverse_allocations(txn)


# ---------------------------------------------------------------------------
# OwnerTransaction services (owner drawings/contributions)
# ---------------------------------------------------------------------------

@transaction.atomic
def create_owner_transaction(
    *, transaction_type: str, amount: Decimal, transaction_date,
    method_allocations: list, note: str = "", user,
) -> OwnerTransaction:
    """
    Records an owner contribution or drawing. Contribution adds to
    CashFlow.cash_in_hand, drawing deducts from it. Unlike investor
    withdrawals, a drawing is NOT capped by net_owner_capital — the owner
    can draw more than they've contributed.
    """
    from rest_framework.exceptions import ValidationError

    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    if transaction_type not in (OwnerTransaction.TransactionType.CONTRIBUTION, OwnerTransaction.TransactionType.DRAWING):
        raise ValidationError({"transaction_type": "Must be 'contribution' or 'drawing'."})
    if not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected."})

    txn = OwnerTransaction.objects.create(
        transaction_type=transaction_type,
        amount=amount,
        transaction_date=transaction_date,
        note=note,
        created_by=user,
        updated_by=user,
    )

    from cash_flow.services import record_cash_movement, sync_owner_contribution, sync_owner_drawing

    if transaction_type == OwnerTransaction.TransactionType.CONTRIBUTION:
        _adjust_cash_management_flow(
            total_owner_contributions_delta=+amount,
            total_owner_contributions_count_delta=+1,
            user=user,
        )
        sync_owner_contribution(amount=amount, user=user)
    else:
        _adjust_cash_management_flow(
            total_owner_drawings_delta=+amount,
            total_owner_withdrawals_count_delta=+1,
            user=user,
        )
        sync_owner_drawing(amount=amount, user=user)

    record_cash_movement(txn)

    from payment_methods.services import record_allocations
    record_allocations(
        txn,
        direction="inflow" if transaction_type == OwnerTransaction.TransactionType.CONTRIBUTION else "outflow",
        splits=method_allocations, total_amount=amount, date=transaction_date, user=user,
    )
    return txn


@transaction.atomic
def delete_owner_transaction(*, pk: int, user) -> None:
    """Soft-deletes an owner transaction and reverses its effects."""
    from django.shortcuts import get_object_or_404

    txn = get_object_or_404(OwnerTransaction, pk=pk, is_deleted=False)
    amount = txn.amount

    from cash_flow.services import reverse_cash_movement, sync_owner_contribution, sync_owner_drawing

    if txn.transaction_type == OwnerTransaction.TransactionType.CONTRIBUTION:
        _adjust_cash_management_flow(
            total_owner_contributions_delta=-amount,
            total_owner_contributions_count_delta=-1,
            user=user,
        )
        sync_owner_drawing(amount=amount, user=user)  # reverse: remove cash_in_hand again
    else:
        _adjust_cash_management_flow(
            total_owner_drawings_delta=-amount,
            total_owner_withdrawals_count_delta=-1,
            user=user,
        )
        sync_owner_contribution(amount=amount, user=user)  # reverse: restore cash_in_hand

    txn.is_deleted = True
    txn.deleted_at = timezone.now()
    txn.deleted_by = user
    txn.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    reverse_cash_movement(txn)

    from payment_methods.services import reverse_allocations
    reverse_allocations(txn)
