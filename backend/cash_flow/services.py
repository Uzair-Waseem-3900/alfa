from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import CashFlow, CashMovement, Expense, ExpenseCategory


# ---------------------------------------------------------------------------
# Internal atomic CashFlow adjuster — NEVER call from outside this module
# ---------------------------------------------------------------------------

def _adjust_cashflow(
    *,
    cash_in_hand_delta                 : Decimal = Decimal("0"),
    total_cash_inflow_delta            : Decimal = Decimal("0"),
    total_cash_outflow_delta           : Decimal = Decimal("0"),
    customer_outstanding_delta         : Decimal = Decimal("0"),
    total_invoices_cash_delta          : Decimal = Decimal("0"),
    total_paid_payables_delta          : Decimal = Decimal("0"),
    supplier_payable_outstanding_delta : Decimal = Decimal("0"),
    total_purchases_cash_delta         : Decimal = Decimal("0"),
    total_expenses_amount_delta        : Decimal = Decimal("0"),
    total_recurring_expenses_paid_delta : Decimal = Decimal("0"),
    total_lost_inventory_worth_delta   : Decimal = Decimal("0"),
    total_lost_inventory_recovered_delta : Decimal = Decimal("0"),
    total_purchase_returns_value_delta : Decimal = Decimal("0"),
    total_purchase_returns_cogs_delta  : Decimal = Decimal("0"),
    total_customer_returns_value_delta : Decimal = Decimal("0"),
    total_customer_returns_cogs_delta  : Decimal = Decimal("0"),
    total_invoice_revenue_delta        : Decimal = Decimal("0"),
    total_invoice_cogs_delta           : Decimal = Decimal("0"),
    total_gross_profit_delta           : Decimal = Decimal("0"),
    total_invoices_count_delta         : int = 0,
    total_purchases_count_delta        : int = 0,
    total_expenses_count_delta         : int = 0,
    user,
) -> CashFlow:
    """
    Atomically adjusts the CashFlow singleton by the given deltas.
    Positive delta = increase. Negative delta = decrease.
    Fields floored at 0 where appropriate.
    This is the ONLY function that writes to CashFlow.

    Field semantics:
        cash_in_hand            = actual cash available (invoice receipts - expenses - supplier payments)
        customer_outstanding    = what customers still owe (increases on confirm, decreases on payment)
        total_invoices_cash     = GROSS invoice receipts ever collected (only ever increases)
        total_paid_payables     = total ever paid to suppliers (only ever increases)
        supplier_payable_outstanding = what we still owe suppliers
        total_purchases_cash    = total purchase value confirmed (paid + outstanding, only ever increases)
        total_expenses_amount   = total expenses recorded
        total_lost_inventory_worth = total FIFO cost of products marked lost, gross (only ever increases)
        total_lost_inventory_recovered = total FIFO cost of lost products later found, gross (only ever increases)
        total_purchase_returns_value = total value of accepted returns to suppliers (only ever increases)
        total_purchase_returns_cogs  = total pre-tax cost of accepted returns to suppliers (only ever increases)
        total_customer_returns_value = total value of accepted returns from customers (only ever increases)
        total_customer_returns_cogs  = total COGS reversed via accepted customer returns (only ever increases)
        total_invoice_revenue   = total grand_total across confirmed invoices (only ever increases)
        total_invoice_cogs      = total COGS across confirmed invoices (only ever increases)
        total_gross_profit      = total gross profit across confirmed invoices (only ever increases)
    """
    with transaction.atomic():
        cf = CashFlow.objects.select_for_update().get_or_create(pk=1)[0]

        # NOT floored at 0 — deliberately, unlike the cumulative counters below.
        #
        # This used to be max(Decimal("0"), ...). When a movement would take
        # cash negative, the deficit was DISCARDED rather than deferred: later
        # inflows then built on the clamped-up figure, so the error was
        # permanent, cumulative, silent, and undetectable after the fact. It
        # also broke the invariant that cash_in_hand equals
        # total_cash_inflow - total_cash_outflow.
        #
        # A negative cash_in_hand is information, not corruption: it means the
        # recorded outflows exceed the recorded inflows, which is a real data
        # problem (a missing receipt, an out-of-order back-dated entry) that
        # someone should see and correct. Showing it is strictly better than
        # silently absorbing it, and it self-corrects the moment the missing
        # inflow is recorded.
        cf.cash_in_hand = cf.cash_in_hand + cash_in_hand_delta
        cf.total_cash_inflow = max(
            Decimal("0"), cf.total_cash_inflow + total_cash_inflow_delta
        )
        cf.total_cash_outflow = max(
            Decimal("0"), cf.total_cash_outflow + total_cash_outflow_delta
        )
        cf.customer_outstanding = max(
            Decimal("0"), cf.customer_outstanding + customer_outstanding_delta
        )
        # total_invoices_cash: gross receipts — floored at 0 but should only increase
        cf.total_invoices_cash = max(
            Decimal("0"), cf.total_invoices_cash + total_invoices_cash_delta
        )
        cf.total_paid_payables = max(
            Decimal("0"), cf.total_paid_payables + total_paid_payables_delta
        )
        cf.supplier_payable_outstanding = max(
            Decimal("0"), cf.supplier_payable_outstanding + supplier_payable_outstanding_delta
        )
        # total_purchases_cash: total purchase value — floored at 0
        cf.total_purchases_cash = max(
            Decimal("0"), cf.total_purchases_cash + total_purchases_cash_delta
        )
        cf.total_expenses_amount = max(
            Decimal("0"), cf.total_expenses_amount + total_expenses_amount_delta
        )
        cf.total_recurring_expenses_paid = max(
            Decimal("0"), cf.total_recurring_expenses_paid + total_recurring_expenses_paid_delta
        )
        cf.total_lost_inventory_worth = max(
            Decimal("0"), cf.total_lost_inventory_worth + total_lost_inventory_worth_delta
        )
        cf.total_lost_inventory_recovered = max(
            Decimal("0"), cf.total_lost_inventory_recovered + total_lost_inventory_recovered_delta
        )
        cf.total_purchase_returns_value = max(
            Decimal("0"), cf.total_purchase_returns_value + total_purchase_returns_value_delta
        )
        cf.total_purchase_returns_cogs = max(
            Decimal("0"), cf.total_purchase_returns_cogs + total_purchase_returns_cogs_delta
        )
        cf.total_customer_returns_value = max(
            Decimal("0"), cf.total_customer_returns_value + total_customer_returns_value_delta
        )
        cf.total_customer_returns_cogs = max(
            Decimal("0"), cf.total_customer_returns_cogs + total_customer_returns_cogs_delta
        )
        cf.total_invoice_revenue = max(
            Decimal("0"), cf.total_invoice_revenue + total_invoice_revenue_delta
        )
        cf.total_invoice_cogs = max(
            Decimal("0"), cf.total_invoice_cogs + total_invoice_cogs_delta
        )
        cf.total_gross_profit = max(
            Decimal("0"), cf.total_gross_profit + total_gross_profit_delta
        )
        cf.total_invoices_count = max(
            0, cf.total_invoices_count + total_invoices_count_delta
        )
        cf.total_purchases_count = max(
            0, cf.total_purchases_count + total_purchases_count_delta
        )
        cf.total_expenses_count = max(
            0, cf.total_expenses_count + total_expenses_count_delta
        )
        cf.last_updated_by = user
        cf.save()
        return cf


# ---------------------------------------------------------------------------
# CashMovement writers — the ONLY code that writes the event table.
#
# Every service that moves cash_in_hand calls record_cash_movement(source)
# right next to its sync_* call (inside the same transaction), passing the
# row that caused the movement. reverse_cash_movement(source) mirrors the
# source's soft-delete; refresh_cash_movement(source) mirrors edits that
# change what the drawer displays (expense edits, advance amount edits).
#
# The payload builders below reproduce EXACTLY the strings the drawer's old
# Python merge built (see get_cash_in_hand_breakdown before this change) —
# they are also what backfill_cash_movements uses to rebuild the table from
# the 14 source models, so live rows and backfilled rows are identical.
# ---------------------------------------------------------------------------

def _payload_opening_cash(e):
    return dict(
        direction="inflow", movement_type="opening_cash",
        date=e.added_at.date(), occurred_at=e.added_at,
        description="Opening cash — data entry", reference=f"OCE-{e.id}",
        amount=e.amount, method=None,
    )


def _payload_invoice_payment(p):
    if p.amount <= 0 or p.invoice.is_deleted:
        return None
    is_advance = p.note.startswith("Advance payment")
    if p.invoice.status == "draft" and not is_advance:
        return None
    return dict(
        direction="inflow",
        movement_type="advance_payment" if is_advance else "invoice_payment",
        date=p.payment_date, occurred_at=p.created_at,
        description=f"Received from {p.invoice.customer.name} ({p.invoice.bill_number})",
        reference=p.reference_number, amount=p.amount, method=p.method,
    )


def _payload_expense(e):
    return dict(
        direction="outflow", movement_type="expense",
        date=e.expense_date, occurred_at=e.created_at,
        description=f"Expense: {e.name} ({e.category.name})",
        reference=f"EXP-{e.id}", amount=e.amount, method=None,
    )


def _payload_supplier_payment(p):
    if p.amount <= 0:
        return None
    ptype = "advance_payment" if p.note.startswith("Advance payment") else "supplier_payment"
    return dict(
        direction="outflow", movement_type=ptype,
        date=p.payment_date, occurred_at=p.created_at,
        description=f"Paid to {p.order.supplier.name} ({p.order.order_number})",
        reference=p.reference_number, amount=p.amount, method=p.method,
    )


def _payload_tax_payment(tp):
    return dict(
        direction="outflow", movement_type="tax_payment",
        date=tp.payment_date, occurred_at=tp.created_at,
        description=f"Tax payment to FBR{f' — {tp.note}' if tp.note else ''}",
        reference=f"TAX-{tp.id}", amount=tp.amount, method=None,
    )


def _payload_wht_payment(wp):
    return dict(
        direction="outflow", movement_type="wht_payment",
        date=wp.payment_date, occurred_at=wp.created_at,
        description=f"WHT payment to FBR{f' — {wp.note}' if wp.note else ''}",
        reference=f"WHT-{wp.id}", amount=wp.amount, method=None,
    )


def _payload_investor_profit_payout(pp):
    return dict(
        direction="outflow", movement_type="investor_profit_payout",
        date=pp.payout_date, occurred_at=pp.created_at,
        description=f"{pp.get_action_type_display()} — {pp.share.investor_name_snapshot} ({pp.share.monthly_profit.period})",
        reference=f"PROFIT-{pp.id}", amount=pp.amount, method=None,
    )


def _payload_owner_profit_payout(op):
    return dict(
        direction="outflow", movement_type="owner_profit_payout",
        date=op.payout_date, occurred_at=op.created_at,
        description=f"{op.get_action_type_display()} — Owner ({op.owner_share.monthly_profit.period})",
        reference=f"OWNPROFIT-{op.id}", amount=op.amount, method=None,
    )


def _payload_cash_adjustment(a):
    is_lost = a.adjustment_type == "lost"
    return dict(
        direction="outflow" if is_lost else "inflow",
        movement_type="cash_lost" if is_lost else "cash_found",
        date=a.adjustment_date, occurred_at=a.created_at,
        description=f"Cash {'lost' if is_lost else 'found'}{f' — {a.reason}' if a.reason else ''}",
        reference=f"ADJ-{a.id}", amount=a.amount, method=None,
    )


def _payload_investor_transaction(t):
    # NOTE: includes is_data_entry rows on purpose — the drawer always
    # itemised every non-deleted InvestorTransaction, even opening
    # investments that never moved cash_in_hand (pre-existing behavior,
    # preserved exactly).
    is_investment = t.transaction_type == "investment"
    return dict(
        direction="inflow" if is_investment else "outflow",
        movement_type="investor_investment" if is_investment else "investor_withdrawal",
        date=t.transaction_date, occurred_at=t.created_at,
        description=f"{'Investment from' if is_investment else 'Withdrawal by'} {t.investor.name}",
        reference=f"INV-{t.id}", amount=t.amount, method=None,
    )


def _payload_owner_transaction(t):
    is_contribution = t.transaction_type == "contribution"
    return dict(
        direction="inflow" if is_contribution else "outflow",
        movement_type="owner_contribution" if is_contribution else "owner_drawing",
        date=t.transaction_date, occurred_at=t.created_at,
        description=f"Owner {'contribution' if is_contribution else 'drawing'}{f' — {t.note}' if t.note else ''}",
        reference=f"OWN-{t.id}", amount=t.amount, method=None,
    )


def _payload_asset(a):
    if a.acquisition_type != "new":
        return None
    return dict(
        direction="outflow", movement_type="asset_purchase",
        date=a.acquisition_date, occurred_at=a.created_at,
        description=f"Fixed asset purchased — {a.name}",
        reference=f"AST-{a.id}", amount=a.cost, method=None,
    )


def _payload_asset_disposal(d):
    if d.disposal_type != "sold":
        return None
    return dict(
        direction="inflow", movement_type="asset_sold",
        date=d.disposal_date, occurred_at=d.created_at,
        description=f"Fixed asset sold — {d.asset.name}",
        reference=f"DIS-{d.id}", amount=d.sale_amount, method=None,
    )


def _payload_recurring_expense_payment(p):
    return dict(
        direction="outflow", movement_type="recurring_expense_payment",
        date=p.payment_date, occurred_at=p.created_at,
        description=f"{p.assignment.name_snapshot} — {p.assignment.period} ({p.assignment.category_name_snapshot})",
        reference=f"REP-{p.id}", amount=p.amount, method=None,
    )


_MOVEMENT_BUILDERS = {
    "data_entry.openingcashentry"                        : _payload_opening_cash,
    "billing.payment"                                    : _payload_invoice_payment,
    "cash_flow.expense"                                  : _payload_expense,
    "purchases.supplierpayment"                          : _payload_supplier_payment,
    "taxes.taxpayment"                                   : _payload_tax_payment,
    "taxes.whtpayment"                                   : _payload_wht_payment,
    "profits.investorprofitpayout"                       : _payload_investor_profit_payout,
    "profits.ownerprofitpayout"                          : _payload_owner_profit_payout,
    "cash_management.cashadjustment"                     : _payload_cash_adjustment,
    "cash_management.investortransaction"                : _payload_investor_transaction,
    "cash_management.ownertransaction"                   : _payload_owner_transaction,
    "assets.asset"                                       : _payload_asset,
    "assets.assetdisposal"                               : _payload_asset_disposal,
    "recurring_expenses.recurringexpenseassignmentpayment": _payload_recurring_expense_payment,
}


def _source_label(source) -> str:
    return f"{source._meta.app_label}.{source._meta.model_name}"


def _movement_payload(source):
    """Payload dict for this source row, or None if the row never appears in
    the drawer (credit notes, non-'new' assets, scrapped disposals, ...)."""
    builder = _MOVEMENT_BUILDERS.get(_source_label(source))
    if builder is None:
        raise ValueError(f"No cash movement builder registered for {_source_label(source)}.")
    return builder(source)


def record_cash_movement(source) -> None:
    """Creates the drawer event for a freshly created source row. Call inside
    the same transaction as the CashFlow sync. No-op if the row doesn't
    belong in the drawer."""
    payload = _movement_payload(source)
    if payload is None:
        return
    CashMovement.objects.create(
        source_model=_source_label(source), source_id=source.pk, **payload,
    )


def refresh_cash_movement(source) -> None:
    """Re-syncs the event after a source edit that changes what the drawer
    shows (expense name/amount/date edits, advance amount edits). Creates,
    updates, revives, or soft-deletes the event as the new payload demands."""
    payload = _movement_payload(source)
    row = CashMovement.objects.filter(
        source_model=_source_label(source), source_id=source.pk,
    ).first()

    if payload is None:
        # e.g. an advance edited down to 0 — the drawer hides amount<=0 rows.
        if row and not row.is_deleted:
            row.is_deleted = True
            row.save(update_fields=["is_deleted"])
        return

    if row is None:
        CashMovement.objects.create(
            source_model=_source_label(source), source_id=source.pk, **payload,
        )
        return

    for field, value in payload.items():
        setattr(row, field, value)
    row.is_deleted = False
    row.save()


def reverse_cash_movement(source) -> None:
    """Soft-deletes the event when its source row is soft-deleted/reversed.
    No-op if no event exists (credit notes, rows predating the event table
    before backfill ran)."""
    CashMovement.objects.filter(
        source_model=_source_label(source), source_id=source.pk, is_deleted=False,
    ).update(is_deleted=True)


# ---------------------------------------------------------------------------
# ExpenseCategory services
# ---------------------------------------------------------------------------

def create_expense_category(*, name: str, description: str = "", user) -> ExpenseCategory:
    from rest_framework.exceptions import ValidationError
    if ExpenseCategory.objects.filter(name__iexact=name.strip()).exists():
        raise ValidationError({"name": "An expense category with this name already exists."})
    return ExpenseCategory.objects.create(
        name=name.strip(),
        description=description,
        created_by=user,
    )


def update_expense_category(*, pk: int, name: str = None, description: str = None, user) -> ExpenseCategory:
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError
    category = get_object_or_404(ExpenseCategory, pk=pk)
    if name:
        qs = ExpenseCategory.objects.filter(name__iexact=name.strip()).exclude(pk=pk)
        if qs.exists():
            raise ValidationError({"name": "An expense category with this name already exists."})
        category.name = name.strip()
    if description is not None:
        category.description = description
    category.save(update_fields=["name", "description"])
    return category


def delete_expense_category(*, pk: int) -> None:
    from django.db.models import ProtectedError
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError
    category = get_object_or_404(ExpenseCategory, pk=pk)
    try:
        category.delete()
    except ProtectedError:
        # Expense.category is on_delete=PROTECT — the DB refuses to delete a
        # category that still has expenses (including soft-deleted ones).
        # Surface that as a friendly 400 instead of an unhandled 500.
        raise ValidationError({
            "detail": "Cannot delete this category — it has expenses recorded against it."
        })


# ---------------------------------------------------------------------------
# Expense services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_expense(
    *, name: str, category_id: int, amount: Decimal,
    expense_date, method_allocations: list, description: str = "", user,
) -> Expense:
    """
    Creates an expense and immediately deducts amount from cash_in_hand.
    Atomic: the Expense row, the CashFlow adjustment, and the drawer event
    commit together or not at all.
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    if amount <= 0:
        raise ValidationError({"amount": "Expense amount must be greater than zero."})
    if not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected."})

    get_object_or_404(ExpenseCategory, pk=category_id)

    expense = Expense.objects.create(
        name=name,
        category_id=category_id,
        amount=amount,
        expense_date=expense_date,
        description=description,
        created_by=user,
        updated_by=user,
    )

    # Deduct from cash_in_hand and add to total_expenses_amount
    _adjust_cashflow(
        cash_in_hand_delta          = -amount,
        total_cash_outflow_delta    = +amount,
        total_expenses_amount_delta = +amount,
        total_expenses_count_delta  = +1,
        user=user,
    )
    record_cash_movement(expense)

    from payment_methods.services import record_allocations
    record_allocations(
        expense, direction="outflow", splits=method_allocations,
        total_amount=amount, date=expense_date, user=user,
    )

    return expense


@transaction.atomic
def update_expense(
    *, pk: int, name: str = None, category_id: int = None,
    amount: Decimal = None, expense_date=None,
    method_allocations: list = None, description: str = None, user,
) -> Expense:
    """
    Updates an expense. If amount changes, adjusts cash_in_hand by the difference.
    Example: old=10000, new=8000 → cash_in_hand += 2000 (refund)
             old=10000, new=12000 → cash_in_hand -= 2000 (extra deduction)
    Atomic: row + CashFlow + drawer event move together.
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    expense = get_object_or_404(Expense, pk=pk, is_deleted=False)
    old_amount = expense.amount

    if name is not None:
        expense.name = name
    if category_id is not None:
        get_object_or_404(ExpenseCategory, pk=category_id)
        expense.category_id = category_id
    if description is not None:
        expense.description = description
    if expense_date is not None:
        expense.expense_date = expense_date
    if amount is not None:
        if amount <= 0:
            raise ValidationError({"amount": "Expense amount must be greater than zero."})
        if amount != old_amount and not method_allocations:
            raise ValidationError({"method_allocations": "At least one method must be selected when the amount changes."})
        expense.amount = amount

    expense.updated_by = user
    expense.save()

    # Adjust cash_in_hand by the difference
    if amount is not None and amount != old_amount:
        delta = old_amount - amount  # positive = refund, negative = extra deduction
        _adjust_cashflow(
            cash_in_hand_delta          = delta,
            total_cash_outflow_delta    = -delta,  # refund = less outflow
            total_expenses_amount_delta = -delta,  # inverse
            user=user,
        )

    # Name/category/date edits change the drawer's display too, not just
    # amount edits — re-sync the event on every update.
    refresh_cash_movement(expense)

    # Re-split explicitly requested (amount change requires it; a method-only
    # correction with the amount unchanged is also allowed).
    if method_allocations:
        from payment_methods.services import refresh_allocations
        refresh_allocations(
            expense, direction="outflow", splits=method_allocations,
            total_amount=expense.amount, date=expense.expense_date, user=user,
        )

    return expense


@transaction.atomic
def delete_expense(*, pk: int, user) -> None:
    """
    Soft-deletes expense and restores its amount to cash_in_hand.
    Atomic: row + CashFlow + drawer event move together.
    """
    from django.shortcuts import get_object_or_404

    expense = get_object_or_404(Expense, pk=pk, is_deleted=False)
    amount  = expense.amount

    expense.is_deleted = True
    expense.deleted_at = timezone.now()
    expense.deleted_by = user
    expense.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    # Restore amount to cash_in_hand
    _adjust_cashflow(
        cash_in_hand_delta          = +amount,
        total_cash_outflow_delta    = -amount,
        total_expenses_amount_delta = -amount,
        total_expenses_count_delta  = -1,
        user=user,
    )
    reverse_cash_movement(expense)

    from payment_methods.services import reverse_allocations
    reverse_allocations(expense)


# ---------------------------------------------------------------------------
# Public sync functions — called by purchases and billing apps
# ---------------------------------------------------------------------------

def sync_invoice_confirmed(
    *, grand_total: Decimal, advance_amount: Decimal = Decimal("0"),
    total_cogs: Decimal = Decimal("0"),
    gross_profit: Decimal = Decimal("0"), user,
) -> None:
    """
    Called when an invoice is confirmed.
    customer_outstanding = grand_total - advance (advance already collected
    on draft creation). total_invoices_cash += advance (it was already
    received from cash_in_hand on draft, mirroring total_paid_payables on
    the purchases side).
    total_invoice_revenue/total_invoice_cogs/total_gross_profit are the
    all-time running totals for the Profit/Margin report — returns don't
    reduce these (Invoice.total_cogs/gross_profit are unaffected by returns,
    confirmed by tracing _recalculate_invoice_totals), so this is the only
    place they're ever incremented.
    """
    _adjust_cashflow(
        customer_outstanding_delta = +(grand_total - advance_amount),
        total_invoices_cash_delta   = +advance_amount,
        total_invoice_revenue_delta = +grand_total,
        total_invoice_cogs_delta    = +total_cogs,
        total_gross_profit_delta    = +gross_profit,
        total_invoices_count_delta  = +1,
        user=user,
    )


def sync_invoice_payment_received(*, amount: Decimal, user) -> None:
    """
    Called when a customer payment is recorded.
    cash_in_hand increases (actual cash received).
    customer_outstanding decreases (they paid us).
    total_invoices_cash increases (gross collection tracker — never reversed).
    """
    _adjust_cashflow(
        cash_in_hand_delta         = +amount,
        total_cash_inflow_delta    = +amount,
        customer_outstanding_delta = -amount,
        total_invoices_cash_delta  = +amount,
        user=user,
    )


def sync_invoice_payment_deleted(*, amount: Decimal, user) -> None:
    """
    Called when a customer payment is deleted.
    Reverses all three fields that were updated on creation.
    Only for positive payments (not credit notes).
    """
    if amount > 0:
        _adjust_cashflow(
            cash_in_hand_delta        = -amount,
            total_cash_inflow_delta   = -amount,
            customer_outstanding_delta= +amount,
            total_invoices_cash_delta = -amount,
            user=user,
        )


def sync_invoice_return_accepted(
    *, return_amount: Decimal, return_cogs: Decimal = Decimal("0"), user,
) -> None:
    """
    Called when a billing return is accepted.
    Customer owes less (credit note) → customer_outstanding decreases.
    No cash movement — goods came back, not money.
    total_customer_returns_value/total_customer_returns_cogs are all-time
    running totals for the Customer Returns report — no reversal path exists
    for an accepted return, so this only ever increases.
    """
    _adjust_cashflow(
        customer_outstanding_delta         = -return_amount,
        total_customer_returns_value_delta = +return_amount,
        total_customer_returns_cogs_delta  = +return_cogs,
        user=user,
    )


def sync_purchase_order_confirmed(*, net_payable: Decimal, advance_amount: Decimal, user) -> None:
    """
    Called when a purchase order is confirmed.
    total_purchases_cash increases by full net_payable (gross purchase value tracker).
    supplier_payable_outstanding = net_payable - advance (advance already paid on draft).
    total_paid_payables += advance (it was already paid from cash_in_hand on draft).
    """
    _adjust_cashflow(
        supplier_payable_outstanding_delta = +(net_payable - advance_amount),
        total_paid_payables_delta          = +advance_amount,
        total_purchases_cash_delta         = +net_payable,
        total_purchases_count_delta        = +1,
        user=user,
    )


def sync_supplier_payment_made(*, amount: Decimal, user) -> None:
    """
    Called when a supplier payment is recorded (non-advance, non-credit-note).
    cash_in_hand decreases (we spent cash).
    supplier_payable_outstanding decreases (we cleared some debt).
    total_paid_payables increases (total ever paid tracker).
    total_purchases_cash does NOT change — already recorded at PO confirmation.
    """
    _adjust_cashflow(
        cash_in_hand_delta                 = -amount,
        total_cash_outflow_delta           = +amount,
        supplier_payable_outstanding_delta = -amount,
        total_paid_payables_delta          = +amount,
        user=user,
    )


def sync_supplier_payment_deleted(*, amount: Decimal, user) -> None:
    """
    Called when a supplier payment record is deleted.
    Reverses all three fields updated on payment creation.
    total_purchases_cash is not touched (PO is still confirmed).
    """
    if amount > 0:
        _adjust_cashflow(
            cash_in_hand_delta                 = +amount,
            total_cash_outflow_delta           = -amount,
            supplier_payable_outstanding_delta = +amount,
            total_paid_payables_delta          = -amount,
            user=user,
        )


def sync_purchase_return_accepted(
    *, return_amount: Decimal, return_cogs: Decimal = Decimal("0"), user,
) -> None:
    """
    Called when a purchase return is accepted.
    We get goods back → supplier owes us less → payable_outstanding decreases.
    total_purchase_returns_value/total_purchase_returns_cogs are the all-time
    running totals for the Purchase Returns report (return_cogs is the
    pre-tax cost portion — total_return_gross — mirroring how
    total_customer_returns_cogs works for symmetry on the dashboard).
    No reversal path exists for an accepted return, so these only increase.
    """
    _adjust_cashflow(
        supplier_payable_outstanding_delta = -return_amount,
        total_purchase_returns_value_delta = +return_amount,
        total_purchase_returns_cogs_delta  = +return_cogs,
        user=user,
    )


def sync_advance_payment_created(*, advance_amount: Decimal, user) -> None:
    """
    Called when a DRAFT purchase order is created with payment_type=advance.
    Immediately deducts advance from cash_in_hand.
    Recorded in payment history separately.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = -advance_amount,
        total_cash_outflow_delta = +advance_amount,
        user=user,
    )


def sync_advance_payment_updated(*, old_amount: Decimal, new_amount: Decimal, user) -> None:
    """
    Called when advance_amount is edited on a draft purchase order.
    Adjusts cash_in_hand by the difference.
    """
    delta = old_amount - new_amount  # positive = refund, negative = extra deduction
    _adjust_cashflow(
        cash_in_hand_delta       = delta,
        total_cash_outflow_delta = -delta,
        user=user,
    )


def sync_invoice_advance_payment_created(*, advance_amount: Decimal, user) -> None:
    """
    Called when a DRAFT invoice is created with payment_type=advance.
    Immediately adds the advance to cash_in_hand (customer paid us early).
    Recorded in payment history separately.
    """
    _adjust_cashflow(
        cash_in_hand_delta      = +advance_amount,
        total_cash_inflow_delta = +advance_amount,
        user=user,
    )


def sync_invoice_advance_payment_updated(*, old_amount: Decimal, new_amount: Decimal, user) -> None:
    """
    Called when advance_amount is edited on a draft invoice.
    Adjusts cash_in_hand by the difference.
    """
    delta = new_amount - old_amount  # positive = extra cash in, negative = refund out
    _adjust_cashflow(
        cash_in_hand_delta      = delta,
        total_cash_inflow_delta = delta,
        user=user,
    )


def sync_invoice_advance_payment_deleted(*, advance_amount: Decimal, user) -> None:
    """
    Called when an advance-payment invoice is deleted (or switched away from
    advance) while still a draft. Reverses the cash addition.
    """
    _adjust_cashflow(
        cash_in_hand_delta      = -advance_amount,
        total_cash_inflow_delta = -advance_amount,
        user=user,
    )


def sync_data_entry_supplier_opening_balance(*, amount: Decimal, user) -> None:
    """
    Data-entry bootstrap: records a supplier opening balance (what we owed a
    supplier before go-live). A carried-forward payable only — it is NOT a
    purchase made in the operating period, so ONLY supplier_payable_outstanding
    increases. total_purchases_cash is deliberately untouched, mirroring the
    customer side (sync_data_entry_customer_opening_balance). No cash movement.
    """
    _adjust_cashflow(
        supplier_payable_outstanding_delta = +amount,
        user=user,
    )


def sync_data_entry_customer_opening_balance(*, amount: Decimal, user) -> None:
    """
    Data-entry bootstrap: records a customer opening balance (what a customer
    owed us before go-live). Only customer_outstanding increases — NO cash was
    received, so total_invoices_cash is deliberately left untouched.
    """
    _adjust_cashflow(
        customer_outstanding_delta = +amount,
        user=user,
    )


def sync_data_entry_opening_cash(*, amount: Decimal, user) -> None:
    """
    Data-entry bootstrap: seeds starting cash on hand. Not an invoice, so only
    cash_in_hand increases — total_invoices_cash is deliberately left untouched.
    """
    _adjust_cashflow(
        cash_in_hand_delta        = +amount,
        total_cash_inflow_delta   = +amount,
        user=user,
    )


def sync_tax_payment_made(*, amount: Decimal, user) -> None:
    """
    Called by taxes.services.create_tax_payment when a GST payment to FBR is
    recorded. Same mechanism as an Expense — it's real cash leaving the till.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = -amount,
        total_cash_outflow_delta = +amount,
        user=user,
    )


def sync_tax_payment_deleted(*, amount: Decimal, user) -> None:
    """
    Called by taxes.services.delete_tax_payment when a GST payment record is
    deleted. Restores the amount to cash_in_hand.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = +amount,
        total_cash_outflow_delta = -amount,
        user=user,
    )


def sync_wht_payment_made(*, amount: Decimal, user) -> None:
    """
    Called by taxes.services.create_wht_payment when a WHT deposit to FBR is
    recorded. Same mechanism as a Tax Payment — it's real cash leaving the till.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = -amount,
        total_cash_outflow_delta = +amount,
        user=user,
    )


def sync_wht_payment_deleted(*, amount: Decimal, user) -> None:
    """
    Called by taxes.services.delete_wht_payment when a WHT payment record is
    deleted. Restores the amount to cash_in_hand.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = +amount,
        total_cash_outflow_delta = -amount,
        user=user,
    )


def sync_investor_profit_payout_made(*, amount: Decimal, user) -> None:
    """
    Called by profits.services.create_investor_profit_payout for EVERY
    settlement action (payout or reinvest) — real cash leaves the till
    either way. For a reinvest, cash_management.services.create_investor_transaction
    brings the same amount back in via its own separate sync call
    immediately after this one, netting to zero — two honest ledger entries,
    not a single no-op.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = -amount,
        total_cash_outflow_delta = +amount,
        user=user,
    )


def sync_investor_profit_payout_reversed(*, amount: Decimal, user) -> None:
    """
    Called by profits.services.delete_investor_profit_payout. Restores the
    amount to cash_in_hand — for a reinvest, the linked InvestorTransaction
    is reversed separately by cash_management.services.delete_investor_transaction.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = +amount,
        total_cash_outflow_delta = -amount,
        user=user,
    )


def sync_owner_profit_payout_made(*, amount: Decimal, user) -> None:
    """
    Called by profits.services.create_owner_profit_payout for EVERY
    settlement action (payout or reinvest) — real cash leaves the till
    either way. For a reinvest, cash_management.services.create_owner_transaction
    brings the same amount back in via its own separate sync call
    immediately after this one, netting to zero — two honest ledger entries,
    not a single no-op. Exact mirror of sync_investor_profit_payout_made.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = -amount,
        total_cash_outflow_delta = +amount,
        user=user,
    )


def sync_owner_profit_payout_reversed(*, amount: Decimal, user) -> None:
    """
    Called by profits.services.delete_owner_profit_payout. Restores the
    amount to cash_in_hand — for a reinvest, the linked OwnerTransaction is
    reversed separately by cash_management.services.delete_owner_transaction.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = +amount,
        total_cash_outflow_delta = -amount,
        user=user,
    )


def sync_cash_lost(*, amount: Decimal, user) -> None:
    """
    Called by cash_management.services when cash is recorded as lost
    (theft, miscount, misplaced). Real cash leaving the till.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = -amount,
        total_cash_outflow_delta = +amount,
        user=user,
    )


def sync_cash_found(*, amount: Decimal, user) -> None:
    """
    Called by cash_management.services when cash is recorded as found/
    recovered (or when reversing a deleted lost entry).
    """
    _adjust_cashflow(
        cash_in_hand_delta     = +amount,
        total_cash_inflow_delta = +amount,
        user=user,
    )


def sync_investor_investment(*, amount: Decimal, user) -> None:
    """
    Called by cash_management.services when an investor puts money into the
    business. Equity financing — increases cash_in_hand only, never
    total_invoice_revenue/total_gross_profit (this is not a sale).
    """
    _adjust_cashflow(
        cash_in_hand_delta     = +amount,
        total_cash_inflow_delta = +amount,
        user=user,
    )


def sync_investor_withdrawal(*, amount: Decimal, user) -> None:
    """
    Called by cash_management.services when an investor withdraws money
    from the business (return of capital).
    """
    _adjust_cashflow(
        cash_in_hand_delta       = -amount,
        total_cash_outflow_delta = +amount,
        user=user,
    )


def sync_owner_contribution(*, amount: Decimal, user) -> None:
    """
    Called by cash_management.services when the owner deposits personal
    money into the business. Equity, same as investor investment — increases
    cash_in_hand only, never total_invoice_revenue/total_gross_profit.
    """
    _adjust_cashflow(
        cash_in_hand_delta     = +amount,
        total_cash_inflow_delta = +amount,
        user=user,
    )


def sync_owner_drawing(*, amount: Decimal, user) -> None:
    """
    Called by cash_management.services when the owner withdraws money for
    personal use. Distinct from lost cash and from investor withdrawals —
    this is deliberate, tracked owner drawings.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = -amount,
        total_cash_outflow_delta = +amount,
        user=user,
    )


def sync_recurring_expense_payment_made(*, amount: Decimal, user) -> None:
    """
    Called by recurring_expenses.services.create_recurring_expense_payment.
    This is the ONLY moment cash actually leaves the business for a
    recurring expense — assigning a month due never touches cash_in_hand.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = -amount,
        total_cash_outflow_delta = +amount,
        total_recurring_expenses_paid_delta = +amount,
        user=user,
    )


def sync_recurring_expense_payment_deleted(*, amount: Decimal, user) -> None:
    """
    Called by recurring_expenses.services.delete_recurring_expense_payment —
    reverses sync_recurring_expense_payment_made exactly.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = +amount,
        total_cash_outflow_delta = -amount,
        total_recurring_expenses_paid_delta = -amount,
        user=user,
    )


def sync_asset_purchased(*, amount: Decimal, user) -> None:
    """
    Called by assets.services.create_asset when a NEW fixed asset is
    purchased (not 'existing'). Real cash leaving the till — the asset
    itself is capitalized, not expensed, so this only touches cash_in_hand.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = -amount,
        total_cash_outflow_delta = +amount,
        user=user,
    )


def sync_asset_sold(*, amount: Decimal, user) -> None:
    """
    Called by assets.services.dispose_asset when a fixed asset is sold.
    Real cash coming in — gain/loss vs book value is tracked separately in
    assets.AssetFlow, not here.
    """
    _adjust_cashflow(
        cash_in_hand_delta     = +amount,
        total_cash_inflow_delta = +amount,
        user=user,
    )


def sync_advance_payment_deleted(*, advance_amount: Decimal, user) -> None:
    """
    Called when a draft purchase order with advance is deleted.
    Restores advance_amount to cash_in_hand.
    """
    _adjust_cashflow(
        cash_in_hand_delta       = +advance_amount,
        total_cash_outflow_delta = -advance_amount,
        user=user,
    )


def sync_lost_inventory_created(*, amount: Decimal, user) -> None:
    """
    Called when a lost inventory record is created.
    total_lost_inventory_worth increases by the batch's FIFO cost.
    A record itself cannot be deleted/undone, but individual items can later
    be marked "found" — see sync_lost_inventory_found, which tracks recovery
    on a separate gross field rather than decrementing this one.
    """
    _adjust_cashflow(
        total_lost_inventory_worth_delta = +amount,
        user=user,
    )


def sync_lost_inventory_found(*, amount: Decimal, user) -> None:
    """
    Called when previously-lost inventory is marked "found" again.
    total_lost_inventory_recovered increases — the dashboard shows the NET
    figure (total_lost_inventory_worth - total_lost_inventory_recovered) as
    "Lost Inventory Worth", so this reduces displayed exposure without ever
    decrementing the gross total_lost_inventory_worth running total.
    """
    _adjust_cashflow(
        total_lost_inventory_recovered_delta = +amount,
        user=user,
    )