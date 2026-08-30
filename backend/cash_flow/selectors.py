from decimal import Decimal

from django.db.models import Q, QuerySet, Sum, Count
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404

from backend.search import search_q
# Shared index-friendly day-boundary helpers (aware datetimes at local
# midnight) — same ones billing/ledger use for datetime-column date filters.
from purchases.selectors import _day_start, _next_day_start

from .models import CashFlow, CashMovement, Expense, ExpenseCategory


# ---------------------------------------------------------------------------
# CashFlow stats (dashboard)
# ---------------------------------------------------------------------------

def get_cashflow_stats() -> dict:
    """
    Returns all dashboard stats from the CashFlow singleton — every number,
    counts included, is a stored field (fully O(1); the counts used to be
    three live COUNT queries over growing tables on every dashboard load).
    """
    cf = CashFlow.get_instance()

    return {
        # Receivables
        # cash_in_hand: actual cash available after expenses and supplier payments
        "cash_in_hand"              : cf.cash_in_hand,
        # customer_outstanding: what customers still owe us
        "customer_outstanding"      : cf.customer_outstanding,
        # total_invoices_cash: GROSS collected from customers (never reduced by expenses/payments)
        "total_invoices_cash"       : cf.total_invoices_cash,
        "total_number_of_invoices"  : cf.total_invoices_count,

        # Payables
        # total_paid_payables: total cash ever paid to suppliers
        "total_paid_payables"           : cf.total_paid_payables,
        # total_outstanding_payable: what we still owe suppliers
        "total_outstanding_payable"     : cf.supplier_payable_outstanding,
        # total_purchases_cash: total purchase value confirmed (paid + outstanding)
        "total_purchases_cash"          : cf.total_purchases_cash,
        "total_number_of_purchases"     : cf.total_purchases_count,

        # Expenses
        "total_expenses_amount"     : cf.total_expenses_amount,
        "total_number_of_expenses"  : cf.total_expenses_count,
        "total_recurring_expenses_paid" : cf.total_recurring_expenses_paid,

        # Lost inventory — gross fields stay gross (never decrease); net is
        # computed here for the dashboard card, mirroring how
        # supplier_payable_outstanding (net) sits alongside total_paid_payables (gross).
        "total_lost_inventory_worth"    : cf.total_lost_inventory_worth,
        "total_lost_inventory_recovered": cf.total_lost_inventory_recovered,
        "net_lost_inventory_worth"      : cf.total_lost_inventory_worth - cf.total_lost_inventory_recovered,

        # Returns
        "total_purchase_returns_value": cf.total_purchase_returns_value,
        "total_purchase_returns_cogs" : cf.total_purchase_returns_cogs,
        "total_customer_returns_value": cf.total_customer_returns_value,
        "total_customer_returns_cogs" : cf.total_customer_returns_cogs,

        # Profit / margin
        # Gross figures are the historical record (what was originally sold,
        # never rewritten by a later return — see Invoice._recalculate_invoice_totals,
        # which sums each item's ORIGINAL line_total/line_cogs regardless of
        # returned_quantity). Net figures subtract the already-tracked
        # total_customer_returns_value/cogs — same "gross stays gross, net
        # computed at read time" pattern as net_lost_inventory_worth above.
        "total_invoice_revenue": cf.total_invoice_revenue,
        "total_invoice_cogs"   : cf.total_invoice_cogs,
        "total_gross_profit"   : cf.total_gross_profit,
        "net_invoice_revenue"  : max(Decimal("0"), cf.total_invoice_revenue - cf.total_customer_returns_value),
        "net_invoice_cogs"     : max(Decimal("0"), cf.total_invoice_cogs - cf.total_customer_returns_cogs),
        "net_gross_profit"     : (
            max(Decimal("0"), cf.total_invoice_revenue - cf.total_customer_returns_value)
            - max(Decimal("0"), cf.total_invoice_cogs - cf.total_customer_returns_cogs)
        ),
    }


# ---------------------------------------------------------------------------
# Expense Category
# ---------------------------------------------------------------------------

def get_all_expense_categories() -> QuerySet:
    # created_by is serialized on every row — select_related avoids one
    # extra query per category (N+1).
    return ExpenseCategory.objects.select_related("created_by").order_by("name")


def get_expense_category_by_id(pk: int) -> ExpenseCategory:
    return get_object_or_404(ExpenseCategory, pk=pk)


# ---------------------------------------------------------------------------
# Expense
# ---------------------------------------------------------------------------

def get_all_expenses(
    *,
    category_id  : int = None,
    date_from    : str = None,
    date_to      : str = None,
    min_amount   : str = None,
    max_amount   : str = None,
    search       : str = None,
) -> QuerySet:
    """
    Returns all non-deleted expenses with full filter support.
    """
    # "category__created_by" (not just "category") because
    # ExpenseCategoryReadSerializer (nested as ExpenseReadSerializer.category)
    # has its own created_by StringRelatedField — without the chained join,
    # every row re-queries the category's creator individually (found via
    # ExpenseAllocationQueryCountTests, pre-existing, unrelated to
    # payment_methods — the same category row was just never being reused
    # across the per-row select_related results).
    qs = Expense.objects.filter(is_deleted=False).select_related(
        "category", "category__created_by", "created_by", "updated_by"
    )

    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name", "description"))
    if category_id:
        qs = qs.filter(category_id=category_id)
    if _clean(date_from):
        qs = qs.filter(expense_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(expense_date__lte=_clean(date_to))
    if _clean(min_amount):
        qs = qs.filter(amount__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(amount__lte=_clean(max_amount))

    return qs.order_by("-expense_date", "-created_at")


def get_expense_by_id(pk: int) -> Expense:
    return get_object_or_404(Expense, pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# Breakdown selectors — for dashboard drill-down
# ---------------------------------------------------------------------------

def get_invoice_payments_breakdown(
    *,
    customer_name  : str = None,
    customer_code  : str = None,
    date_from      : str = None,
    date_to        : str = None,
    min_amount     : str = None,
    max_amount     : str = None,
    method         : str = None,
) -> QuerySet:
    """
    Breakdown of all POSITIVE invoice payments received from customers.
    This is the total_invoices_cash breakdown (gross collections only).
    Includes advance payments on draft invoices — mirrors
    get_supplier_payments_breakdown, which includes supplier advances the
    same way for total_paid_payables.

    NOTE: an advance payment's amount is only folded into
    CashFlow.total_invoices_cash at invoice CONFIRMATION (sync_invoice_confirmed),
    not at draft creation (sync_invoice_advance_payment_created only touches
    cash_in_hand). So while an advance invoice is still draft, this breakdown's
    sum can be temporarily higher than the total_invoices_cash card it drills
    into — intentional, self-corrects on confirm or delete, mirrors the same
    lag on the purchases/total_paid_payables side.
    For full cash_in_hand movements (expenses, supplier payments) use get_cash_in_hand_breakdown().
    """
    from billing.models import Payment

    qs = Payment.objects.filter(
        is_deleted=False,
        amount__gt=0,
        invoice__is_deleted=False,
    ).select_related("invoice__customer", "created_by")

    if _clean(customer_name):
        qs = qs.filter(search_q(_clean(customer_name), "invoice__customer__name"))
    if _clean(customer_code):
        qs = qs.filter(search_q(_clean(customer_code), "invoice__customer__code"))
    if _clean(date_from):
        qs = qs.filter(payment_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(payment_date__lte=_clean(date_to))
    if _clean(min_amount):
        qs = qs.filter(amount__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(amount__lte=_clean(max_amount))
    if _clean(method):
        qs = qs.filter(method=_clean(method))

    return qs.order_by("-created_at")


def get_cash_in_hand_breakdown(
    *,
    date_from    : str = None,
    date_to      : str = None,
    movement_type: str = None,
) -> QuerySet:
    """
    Full cash_in_hand breakdown — ALL movements (inflows AND outflows),
    served by ONE indexed query on the CashMovement event table (each event
    is written in the same transaction as its CashFlow adjustment; see
    services.record_cash_movement). Previously this materialized EVERY row
    from 14 source tables into Python dicts and sorted them on each drawer
    open — O(all history) per request. Now O(page).

    movement_type: inflow | outflow (optional filter)
    Returns a queryset ordered newest first (by occurred_at — the source
    row's creation time, NOT the business date, which can be backdated —
    same ordering as before).
    """
    qs = CashMovement.objects.filter(is_deleted=False)

    if _clean(date_from):
        qs = qs.filter(date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(date__lte=_clean(date_to))
    if _clean(movement_type):
        qs = qs.filter(direction=_clean(movement_type))

    return qs.order_by("-occurred_at", "-id")


def get_cash_in_hand_breakdown_from_sources(
    *,
    date_from    : str = None,
    date_to      : str = None,
    movement_type: str = None,
) -> list:
    """
    The ORIGINAL 14-source Python merge, kept verbatim as the consistency
    oracle: backfill_cash_movements rebuilds the event table from it, and
    tests assert the event table returns the exact same rows. Never called
    on a request path.
    """
    from billing.models import Payment
    from purchases.models import SupplierPayment
    from .models import Expense

    movements = []

    # --- Inflows: opening cash (data-entry bootstrap) ---
    # data_entry is a removable bootstrap app. Import defensively so this
    # breakdown keeps working after the app (and its table) are removed
    # post-go-live — it simply stops itemising opening-cash inflows.
    try:
        from data_entry.models import OpeningCashEntry
        oc_qs = OpeningCashEntry.objects.all()
        if _clean(date_from):
            oc_qs = oc_qs.filter(added_at__date__gte=_clean(date_from))
        if _clean(date_to):
            oc_qs = oc_qs.filter(added_at__date__lte=_clean(date_to))
        for e in oc_qs:
            movements.append({
                "direction"  : "inflow",
                "type"       : "opening_cash",
                "date"       : str(e.added_at.date()),
                "created_at" : e.added_at,
                "description": "Opening cash — data entry",
                "reference"  : f"OCE-{e.id}",
                "amount"     : e.amount,
                "method"     : None,
            })
    except Exception:
        pass

    # --- Inflows: positive invoice payments ---
    # No draft-status exclusion (unlike a plain regular payment, an advance
    # payment DOES exist on a draft invoice) — advance vs regular is
    # distinguished by the note prefix instead, mirroring sup_qs below.
    inv_qs = Payment.objects.filter(
        is_deleted=False, amount__gt=0,
        invoice__is_deleted=False,
    ).filter(
        Q(note__startswith="Advance payment") | ~Q(invoice__status="draft")
    ).select_related("invoice__customer")

    if _clean(date_from):
        inv_qs = inv_qs.filter(payment_date__gte=_clean(date_from))
    if _clean(date_to):
        inv_qs = inv_qs.filter(payment_date__lte=_clean(date_to))

    for p in inv_qs:
        ptype = "advance_payment" if p.note.startswith("Advance payment") else "invoice_payment"
        movements.append({
            "direction"  : "inflow",
            "type"       : ptype,
            "date"       : str(p.payment_date),
            "created_at" : p.created_at,
            "description": f"Received from {p.invoice.customer.name} ({p.invoice.bill_number})",
            "reference"  : p.reference_number,
            "amount"     : p.amount,
            "method"     : p.method,
        })

    # --- Outflows: expenses ---
    exp_qs = Expense.objects.filter(is_deleted=False)
    if _clean(date_from):
        exp_qs = exp_qs.filter(expense_date__gte=_clean(date_from))
    if _clean(date_to):
        exp_qs = exp_qs.filter(expense_date__lte=_clean(date_to))

    for e in exp_qs:
        movements.append({
            "direction"  : "outflow",
            "type"       : "expense",
            "date"       : str(e.expense_date),
            "created_at" : e.created_at,
            "description": f"Expense: {e.name} ({e.category.name})",
            "reference"  : f"EXP-{e.id}",
            "amount"     : e.amount,
            "method"     : None,
        })

    # --- Outflows: supplier payments ---
    sup_qs = SupplierPayment.objects.filter(
        is_deleted=False, amount__gt=0,
    ).select_related("order__supplier")
    if _clean(date_from):
        sup_qs = sup_qs.filter(payment_date__gte=_clean(date_from))
    if _clean(date_to):
        sup_qs = sup_qs.filter(payment_date__lte=_clean(date_to))

    for p in sup_qs:
        ptype = "advance_payment" if p.note.startswith("Advance payment") else "supplier_payment"
        movements.append({
            "direction"  : "outflow",
            "type"       : ptype,
            "date"       : str(p.payment_date),
            "created_at" : p.created_at,
            "description": f"Paid to {p.order.supplier.name} ({p.order.order_number})",
            "reference"  : p.reference_number,
            "amount"     : p.amount,
            "method"     : p.method,
        })

    # --- Outflows: tax payments (GST paid to FBR) ---
    # taxes is a separate app — import defensively so this breakdown keeps
    # working even if the app were ever removed.
    try:
        from taxes.models import TaxPayment
        tax_qs = TaxPayment.objects.filter(is_deleted=False)
        if _clean(date_from):
            tax_qs = tax_qs.filter(payment_date__gte=_clean(date_from))
        if _clean(date_to):
            tax_qs = tax_qs.filter(payment_date__lte=_clean(date_to))

        for tp in tax_qs:
            movements.append({
                "direction"  : "outflow",
                "type"       : "tax_payment",
                "date"       : str(tp.payment_date),
                "created_at" : tp.created_at,
                "description": f"Tax payment to FBR{f' — {tp.note}' if tp.note else ''}",
                "reference"  : f"TAX-{tp.id}",
                "amount"     : tp.amount,
                "method"     : None,
            })
    except Exception:
        pass

    # --- Outflows: WHT payments (withholding tax deposited to FBR) ---
    try:
        from taxes.models import WHTPayment
        wht_qs = WHTPayment.objects.filter(is_deleted=False)
        if _clean(date_from):
            wht_qs = wht_qs.filter(payment_date__gte=_clean(date_from))
        if _clean(date_to):
            wht_qs = wht_qs.filter(payment_date__lte=_clean(date_to))

        for wp in wht_qs:
            movements.append({
                "direction"  : "outflow",
                "type"       : "wht_payment",
                "date"       : str(wp.payment_date),
                "created_at" : wp.created_at,
                "description": f"WHT payment to FBR{f' — {wp.note}' if wp.note else ''}",
                "reference"  : f"WHT-{wp.id}",
                "amount"     : wp.amount,
                "method"     : None,
            })
    except Exception:
        pass

    # --- Outflows: investor profit payouts (payout or reinvest — both move cash out) ---
    try:
        from profits.models import InvestorProfitPayout
        payout_qs = InvestorProfitPayout.objects.filter(is_deleted=False).select_related(
            "share__investor",
        )
        if _clean(date_from):
            payout_qs = payout_qs.filter(payout_date__gte=_clean(date_from))
        if _clean(date_to):
            payout_qs = payout_qs.filter(payout_date__lte=_clean(date_to))

        for pp in payout_qs:
            movements.append({
                "direction"  : "outflow",
                "type"       : "investor_profit_payout",
                "date"       : str(pp.payout_date),
                "created_at" : pp.created_at,
                "description": f"{pp.get_action_type_display()} — {pp.share.investor_name_snapshot} ({pp.share.monthly_profit.period})",
                "reference"  : f"PROFIT-{pp.id}",
                "amount"     : pp.amount,
                "method"     : None,
            })
    except Exception:
        pass

    # --- Outflows: owner profit payouts (payout or reinvest — both move cash out) ---
    try:
        from profits.models import OwnerProfitPayout
        owner_payout_qs = OwnerProfitPayout.objects.filter(is_deleted=False).select_related(
            "owner_share__monthly_profit",
        )
        if _clean(date_from):
            owner_payout_qs = owner_payout_qs.filter(payout_date__gte=_clean(date_from))
        if _clean(date_to):
            owner_payout_qs = owner_payout_qs.filter(payout_date__lte=_clean(date_to))

        for op in owner_payout_qs:
            movements.append({
                "direction"  : "outflow",
                "type"       : "owner_profit_payout",
                "date"       : str(op.payout_date),
                "created_at" : op.created_at,
                "description": f"{op.get_action_type_display()} — Owner ({op.owner_share.monthly_profit.period})",
                "reference"  : f"OWNPROFIT-{op.id}",
                "amount"     : op.amount,
                "method"     : None,
            })
    except Exception:
        pass

    # --- Lost/found cash + investor investments/withdrawals ---
    # cash_management is a separate app — import defensively so this
    # breakdown keeps working even if the app were ever removed.
    try:
        from cash_management.models import CashAdjustment, InvestorTransaction, OwnerTransaction

        adj_qs = CashAdjustment.objects.filter(is_deleted=False)
        if _clean(date_from):
            adj_qs = adj_qs.filter(adjustment_date__gte=_clean(date_from))
        if _clean(date_to):
            adj_qs = adj_qs.filter(adjustment_date__lte=_clean(date_to))

        for a in adj_qs:
            is_lost = a.adjustment_type == CashAdjustment.AdjustmentType.LOST
            movements.append({
                "direction"  : "outflow" if is_lost else "inflow",
                "type"       : "cash_lost" if is_lost else "cash_found",
                "date"       : str(a.adjustment_date),
                "created_at" : a.created_at,
                "description": f"Cash {'lost' if is_lost else 'found'}{f' — {a.reason}' if a.reason else ''}",
                "reference"  : f"ADJ-{a.id}",
                "amount"     : a.amount,
                "method"     : None,
            })

        inv_txn_qs = InvestorTransaction.objects.filter(is_deleted=False).select_related("investor")
        if _clean(date_from):
            inv_txn_qs = inv_txn_qs.filter(transaction_date__gte=_clean(date_from))
        if _clean(date_to):
            inv_txn_qs = inv_txn_qs.filter(transaction_date__lte=_clean(date_to))

        for t in inv_txn_qs:
            is_investment = t.transaction_type == InvestorTransaction.TransactionType.INVESTMENT
            movements.append({
                "direction"  : "inflow" if is_investment else "outflow",
                "type"       : "investor_investment" if is_investment else "investor_withdrawal",
                "date"       : str(t.transaction_date),
                "created_at" : t.created_at,
                "description": f"{'Investment from' if is_investment else 'Withdrawal by'} {t.investor.name}",
                "reference"  : f"INV-{t.id}",
                "amount"     : t.amount,
                "method"     : None,
            })

        owner_txn_qs = OwnerTransaction.objects.filter(is_deleted=False)
        if _clean(date_from):
            owner_txn_qs = owner_txn_qs.filter(transaction_date__gte=_clean(date_from))
        if _clean(date_to):
            owner_txn_qs = owner_txn_qs.filter(transaction_date__lte=_clean(date_to))

        for t in owner_txn_qs:
            is_contribution = t.transaction_type == OwnerTransaction.TransactionType.CONTRIBUTION
            movements.append({
                "direction"  : "inflow" if is_contribution else "outflow",
                "type"       : "owner_contribution" if is_contribution else "owner_drawing",
                "date"       : str(t.transaction_date),
                "created_at" : t.created_at,
                "description": f"Owner {'contribution' if is_contribution else 'drawing'}{f' — {t.note}' if t.note else ''}",
                "reference"  : f"OWN-{t.id}",
                "amount"     : t.amount,
                "method"     : None,
            })
    except Exception:
        pass

    # --- Fixed asset purchases (outflow) + sold disposals (inflow) ---
    # assets is a separate app — import defensively so this breakdown keeps
    # working even if the app were ever removed.
    try:
        from assets.models import Asset, AssetDisposal

        asset_qs = Asset.objects.filter(is_deleted=False, acquisition_type=Asset.AcquisitionType.NEW)
        if _clean(date_from):
            asset_qs = asset_qs.filter(acquisition_date__gte=_clean(date_from))
        if _clean(date_to):
            asset_qs = asset_qs.filter(acquisition_date__lte=_clean(date_to))

        for a in asset_qs:
            movements.append({
                "direction"  : "outflow",
                "type"       : "asset_purchase",
                "date"       : str(a.acquisition_date),
                "created_at" : a.created_at,
                "description": f"Fixed asset purchased — {a.name}",
                "reference"  : f"AST-{a.id}",
                "amount"     : a.cost,
                "method"     : None,
            })

        sold_qs = AssetDisposal.objects.filter(disposal_type=AssetDisposal.DisposalType.SOLD).select_related("asset")
        if _clean(date_from):
            sold_qs = sold_qs.filter(disposal_date__gte=_clean(date_from))
        if _clean(date_to):
            sold_qs = sold_qs.filter(disposal_date__lte=_clean(date_to))

        for d in sold_qs:
            movements.append({
                "direction"  : "inflow",
                "type"       : "asset_sold",
                "date"       : str(d.disposal_date),
                "created_at" : d.created_at,
                "description": f"Fixed asset sold — {d.asset.name}",
                "reference"  : f"DIS-{d.id}",
                "amount"     : d.sale_amount,
                "method"     : None,
            })
    except Exception:
        pass

    # --- Outflows: recurring expense payments (salaries, rent, ...) ---
    # recurring_expenses is a separate app — import defensively so this
    # breakdown keeps working even if the app were ever removed.
    try:
        from recurring_expenses.models import RecurringExpenseAssignmentPayment

        rep_qs = RecurringExpenseAssignmentPayment.objects.filter(is_deleted=False).select_related("assignment")
        if _clean(date_from):
            rep_qs = rep_qs.filter(payment_date__gte=_clean(date_from))
        if _clean(date_to):
            rep_qs = rep_qs.filter(payment_date__lte=_clean(date_to))

        for p in rep_qs:
            movements.append({
                "direction"  : "outflow",
                "type"       : "recurring_expense_payment",
                "date"       : str(p.payment_date),
                "created_at" : p.created_at,
                "description": f"{p.assignment.name_snapshot} — {p.assignment.period} ({p.assignment.category_name_snapshot})",
                "reference"  : f"REP-{p.id}",
                "amount"     : p.amount,
                "method"     : None,
            })
    except Exception:
        pass

    # Filter by direction if requested
    if _clean(movement_type):
        movements = [m for m in movements if m["direction"] == _clean(movement_type)]

    # Sort by created_at (record creation time), newest first — NOT by the
    # business "date" field, which can differ from when the record was
    # actually entered (e.g. a payment backdated to an earlier date).
    movements.sort(key=lambda x: x["created_at"], reverse=True)
    return movements


def get_cash_flow_totals_up_to(as_of_date=None) -> dict:
    """
    {"inflow": Decimal, "outflow": Decimal} summed at the DB level (Sum/
    Coalesce per source, no per-row dict building) across the same 14
    sources get_cash_in_hand_breakdown() draws from. `as_of_date=None` means
    unbounded (all-time) — used by the backfill command and by
    get_cash_in_hand_as_of() below, which is the only place this runs with a
    date bound, and only on-demand from the opening/closing cash filter
    (never on a page that loads by default), see instructions/architecture.md.
    """
    from billing.models import Payment
    from purchases.models import SupplierPayment
    from .models import Expense

    zero = Decimal("0")
    inflow = zero
    outflow = zero

    def _lte(qs, field):
        return qs.filter(**{f"{field}__lte": as_of_date}) if as_of_date is not None else qs

    def _sum(qs, field="amount"):
        return qs.aggregate(s=Coalesce(Sum(field), zero))["s"]

    try:
        from data_entry.models import OpeningCashEntry
        # added_at is a datetime — use a half-open bound at the next local
        # midnight instead of the index-defeating __date cast.
        oc_qs = OpeningCashEntry.objects.all()
        if as_of_date is not None:
            oc_qs = oc_qs.filter(added_at__lt=_next_day_start(as_of_date))
        inflow += _sum(oc_qs)
    except Exception:
        pass

    inflow += _sum(_lte(Payment.objects.filter(
        is_deleted=False, amount__gt=0, invoice__is_deleted=False,
    ).filter(
        Q(note__startswith="Advance payment") | ~Q(invoice__status="draft")
    ), "payment_date"))

    outflow += _sum(_lte(Expense.objects.filter(is_deleted=False), "expense_date"))

    outflow += _sum(_lte(SupplierPayment.objects.filter(
        is_deleted=False, amount__gt=0,
    ), "payment_date"))

    try:
        from taxes.models import TaxPayment, WHTPayment
        outflow += _sum(_lte(TaxPayment.objects.filter(is_deleted=False), "payment_date"))
        outflow += _sum(_lte(WHTPayment.objects.filter(is_deleted=False), "payment_date"))
    except Exception:
        pass

    try:
        from profits.models import InvestorProfitPayout
        outflow += _sum(_lte(InvestorProfitPayout.objects.filter(is_deleted=False), "payout_date"))
    except Exception:
        pass

    try:
        from profits.models import OwnerProfitPayout
        outflow += _sum(_lte(OwnerProfitPayout.objects.filter(is_deleted=False), "payout_date"))
    except Exception:
        pass

    try:
        from cash_management.models import CashAdjustment, InvestorTransaction, OwnerTransaction

        inflow += _sum(_lte(CashAdjustment.objects.filter(
            is_deleted=False, adjustment_type=CashAdjustment.AdjustmentType.FOUND,
        ), "adjustment_date"))
        outflow += _sum(_lte(CashAdjustment.objects.filter(
            is_deleted=False, adjustment_type=CashAdjustment.AdjustmentType.LOST,
        ), "adjustment_date"))

        inflow += _sum(_lte(InvestorTransaction.objects.filter(
            is_deleted=False, transaction_type=InvestorTransaction.TransactionType.INVESTMENT,
        ), "transaction_date"))
        outflow += _sum(_lte(InvestorTransaction.objects.filter(
            is_deleted=False, transaction_type=InvestorTransaction.TransactionType.WITHDRAWAL,
        ), "transaction_date"))

        inflow += _sum(_lte(OwnerTransaction.objects.filter(
            is_deleted=False, transaction_type=OwnerTransaction.TransactionType.CONTRIBUTION,
        ), "transaction_date"))
        outflow += _sum(_lte(OwnerTransaction.objects.filter(
            is_deleted=False, transaction_type=OwnerTransaction.TransactionType.DRAWING,
        ), "transaction_date"))
    except Exception:
        pass

    try:
        from assets.models import Asset, AssetDisposal
        outflow += _sum(_lte(Asset.objects.filter(
            is_deleted=False, acquisition_type=Asset.AcquisitionType.NEW,
        ), "acquisition_date"), field="cost")
        inflow += _sum(_lte(AssetDisposal.objects.filter(
            disposal_type=AssetDisposal.DisposalType.SOLD,
        ), "disposal_date"), field="sale_amount")
    except Exception:
        pass

    try:
        from recurring_expenses.models import RecurringExpenseAssignmentPayment
        outflow += _sum(_lte(RecurringExpenseAssignmentPayment.objects.filter(
            is_deleted=False,
        ), "payment_date"))
    except Exception:
        pass

    return {"inflow": inflow, "outflow": outflow}


def get_cash_in_hand_as_of(as_of_date) -> Decimal:
    """
    Cash-in-hand balance as it stood at the end of `as_of_date` (inclusive).
    """
    totals = get_cash_flow_totals_up_to(as_of_date)
    return totals["inflow"] - totals["outflow"]


def get_opening_closing_cash(*, date_from: str, date_to: str) -> dict:
    """
    Opening cash = balance right before `date_from` starts.
    Closing cash = balance at the end of `date_to` — except when `date_to`
    is today or later, since today isn't finished yet: return the live
    CashFlow.cash_in_hand instead of aggregating (equivalent value, O(1)).
    """
    from datetime import date as date_cls, timedelta

    date_from_parsed = date_cls.fromisoformat(str(date_from))
    date_to_parsed = date_cls.fromisoformat(str(date_to))

    opening = get_cash_in_hand_as_of(date_from_parsed - timedelta(days=1))

    if date_to_parsed >= date_cls.today():
        closing = CashFlow.get_instance().cash_in_hand
    else:
        closing = get_cash_in_hand_as_of(date_to_parsed)

    return {"opening_cash": opening, "closing_cash": closing}


def get_customer_outstanding_breakdown(
    *,
    customer_name  : str = None,
    customer_code  : str = None,
    payment_status : str = None,
    date_from      : str = None,
    date_to        : str = None,
    min_amount     : str = None,
    max_amount     : str = None,
) -> QuerySet:
    """
    Breakdown of all invoices with outstanding balance (customer_outstanding drill-down).
    """
    from billing.models import Invoice

    qs = Invoice.objects.filter(
        is_deleted=False,
        credit_outstanding__gt=0,
    ).exclude(status="draft").select_related("customer")

    if _clean(customer_name):
        qs = qs.filter(search_q(_clean(customer_name), "customer__name"))
    if _clean(customer_code):
        qs = qs.filter(search_q(_clean(customer_code), "customer__code"))
    if _clean(payment_status):
        qs = qs.filter(payment_status=_clean(payment_status))
    if _clean(date_from) and _day_start(_clean(date_from)):
        qs = qs.filter(created_at__gte=_day_start(_clean(date_from)))
    if _clean(date_to) and _next_day_start(_clean(date_to)):
        qs = qs.filter(created_at__lt=_next_day_start(_clean(date_to)))
    if _clean(min_amount):
        qs = qs.filter(credit_outstanding__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(credit_outstanding__lte=_clean(max_amount))

    return qs.order_by("-credit_outstanding")


def get_supplier_payments_breakdown(
    *,
    supplier_name : str = None,
    supplier_code : str = None,
    date_from     : str = None,
    date_to       : str = None,
    min_amount    : str = None,
    max_amount    : str = None,
    method        : str = None,
) -> QuerySet:
    """
    Breakdown of all supplier payments made (total_paid_payables drill-down).
    """
    from purchases.models import SupplierPayment

    qs = SupplierPayment.objects.filter(
        is_deleted=False,
        amount__gt=0,
    ).select_related("order__supplier", "created_by")

    if _clean(supplier_name):
        qs = qs.filter(search_q(_clean(supplier_name), "order__supplier__name"))
    if _clean(supplier_code):
        qs = qs.filter(search_q(_clean(supplier_code), "order__supplier__code"))
    if _clean(date_from):
        qs = qs.filter(payment_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(payment_date__lte=_clean(date_to))
    if _clean(min_amount):
        qs = qs.filter(amount__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(amount__lte=_clean(max_amount))
    if _clean(method):
        qs = qs.filter(method=_clean(method))

    return qs.order_by("-created_at")


def get_supplier_payable_outstanding_breakdown(
    *,
    supplier_name  : str = None,
    supplier_code  : str = None,
    payment_status : str = None,
    date_from      : str = None,
    date_to        : str = None,
    min_amount     : str = None,
    max_amount     : str = None,
) -> QuerySet:
    """
    Breakdown of all purchase orders with outstanding payable
    (supplier_payable_outstanding drill-down).
    """
    from purchases.models import PurchaseOrder

    qs = PurchaseOrder.objects.filter(
        is_deleted=False,
        status="confirmed",
        payable_outstanding__gt=0,
    ).select_related("supplier")

    if _clean(supplier_name):
        qs = qs.filter(search_q(_clean(supplier_name), "supplier__name"))
    if _clean(supplier_code):
        qs = qs.filter(search_q(_clean(supplier_code), "supplier__code"))
    if _clean(payment_status):
        qs = qs.filter(payment_status=_clean(payment_status))
    if _clean(date_from) and _day_start(_clean(date_from)):
        qs = qs.filter(created_at__gte=_day_start(_clean(date_from)))
    if _clean(date_to) and _next_day_start(_clean(date_to)):
        qs = qs.filter(created_at__lt=_next_day_start(_clean(date_to)))
    if _clean(min_amount):
        qs = qs.filter(payable_outstanding__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(payable_outstanding__lte=_clean(max_amount))

    return qs.order_by("-payable_outstanding")


def get_invoices_breakdown(
    *,
    customer_name  : str = None,
    customer_code  : str = None,
    payment_status : str = None,
    status         : str = None,
    date_from      : str = None,
    date_to        : str = None,
    min_amount     : str = None,
    max_amount     : str = None,
) -> QuerySet:
    """
    Full invoice breakdown for the total_number_of_invoices drill-down.
    """
    from billing.models import Invoice

    qs = Invoice.objects.filter(
        is_deleted=False,
        is_data_entry=False,
    ).exclude(status="draft").select_related("customer")

    if _clean(customer_name):
        qs = qs.filter(search_q(_clean(customer_name), "customer__name"))
    if _clean(customer_code):
        qs = qs.filter(search_q(_clean(customer_code), "customer__code"))
    if _clean(payment_status):
        qs = qs.filter(payment_status=_clean(payment_status))
    if _clean(status):
        qs = qs.filter(status=_clean(status))
    if _clean(date_from) and _day_start(_clean(date_from)):
        qs = qs.filter(created_at__gte=_day_start(_clean(date_from)))
    if _clean(date_to) and _next_day_start(_clean(date_to)):
        qs = qs.filter(created_at__lt=_next_day_start(_clean(date_to)))
    if _clean(min_amount):
        qs = qs.filter(grand_total__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(grand_total__lte=_clean(max_amount))

    return qs.order_by("-created_at")


def get_purchases_breakdown(
    *,
    supplier_name  : str = None,
    supplier_code  : str = None,
    payment_status : str = None,
    date_from      : str = None,
    date_to        : str = None,
    min_amount     : str = None,
    max_amount     : str = None,
) -> QuerySet:
    """
    Full purchase order breakdown for total_number_of_purchases drill-down.
    """
    from purchases.models import PurchaseOrder

    # Opening balances are carried-forward payables, not operating-period
    # purchases — excluded here (mirrors the invoices breakdown on the sales
    # side). is_data_entry=False also covers opening stock (SYS-OPENING).
    qs = PurchaseOrder.objects.filter(
        is_deleted=False,
        is_data_entry=False,
        status="confirmed",
    ).select_related("supplier")

    if _clean(supplier_name):
        qs = qs.filter(search_q(_clean(supplier_name), "supplier__name"))
    if _clean(supplier_code):
        qs = qs.filter(search_q(_clean(supplier_code), "supplier__code"))
    if _clean(payment_status):
        qs = qs.filter(payment_status=_clean(payment_status))
    if _clean(date_from) and _day_start(_clean(date_from)):
        qs = qs.filter(created_at__gte=_day_start(_clean(date_from)))
    if _clean(date_to) and _next_day_start(_clean(date_to)):
        qs = qs.filter(created_at__lt=_next_day_start(_clean(date_to)))
    if _clean(min_amount):
        qs = qs.filter(net_payable__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(net_payable__lte=_clean(max_amount))

    return qs.order_by("-created_at")


def get_lost_inventory_breakdown(
    *,
    search     : str = None,
    product_id : str = None,
    date_from  : str = None,
    date_to    : str = None,
) -> QuerySet:
    """
    Breakdown of every lost-inventory line item (total_lost_inventory_worth drill-down).
    Flattened to item level (not record level) so each row shows one product's loss.
    """
    from purchases.models import LostInventoryItem

    qs = LostInventoryItem.objects.filter(
        record__is_deleted=False,
    ).select_related("record", "record__created_by", "product")

    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "record__reference_number"))
    if _clean(product_id):
        qs = qs.filter(product_id=_clean(product_id))
    if _clean(date_from) and _day_start(_clean(date_from)):
        qs = qs.filter(record__created_at__gte=_day_start(_clean(date_from)))
    if _clean(date_to) and _next_day_start(_clean(date_to)):
        qs = qs.filter(record__created_at__lt=_next_day_start(_clean(date_to)))

    return qs.order_by("-record__created_at")


# ---------------------------------------------------------------------------
# Purchase returns breakdown (total_purchase_returns_value/cogs drill-down)
# ---------------------------------------------------------------------------

def get_purchase_returns_breakdown(
    *,
    supplier_name : str = None,
    supplier_code : str = None,
    date_from     : str = None,
    date_to       : str = None,
) -> QuerySet:
    """
    Full breakdown of accepted returns to suppliers
    (total_purchase_returns_value / total_purchase_returns_cogs drill-down).
    """
    from purchases.models import PurchaseReturn

    qs = PurchaseReturn.objects.filter(
        is_deleted=False, status=PurchaseReturn.Status.ACCEPTED,
    ).select_related("order__supplier")

    if _clean(supplier_name):
        qs = qs.filter(search_q(_clean(supplier_name), "order__supplier__name"))
    if _clean(supplier_code):
        qs = qs.filter(search_q(_clean(supplier_code), "order__supplier__code"))
    if _clean(date_from) and _day_start(_clean(date_from)):
        qs = qs.filter(accepted_at__gte=_day_start(_clean(date_from)))
    if _clean(date_to) and _next_day_start(_clean(date_to)):
        qs = qs.filter(accepted_at__lt=_next_day_start(_clean(date_to)))

    return qs.order_by("-created_at")


# ---------------------------------------------------------------------------
# Customer returns breakdown (total_customer_returns_value/cogs drill-down)
# ---------------------------------------------------------------------------

def get_customer_returns_breakdown(
    *,
    customer_name : str = None,
    customer_code : str = None,
    date_from     : str = None,
    date_to       : str = None,
) -> QuerySet:
    """
    Full breakdown of accepted returns from customers
    (total_customer_returns_value / total_customer_returns_cogs drill-down).
    """
    from billing.models import Return

    qs = Return.objects.filter(
        is_deleted=False, status=Return.Status.ACCEPTED,
    ).select_related("invoice__customer")

    if _clean(customer_name):
        qs = qs.filter(search_q(_clean(customer_name), "invoice__customer__name"))
    if _clean(customer_code):
        qs = qs.filter(search_q(_clean(customer_code), "invoice__customer__code"))
    if _clean(date_from) and _day_start(_clean(date_from)):
        qs = qs.filter(accepted_at__gte=_day_start(_clean(date_from)))
    if _clean(date_to) and _next_day_start(_clean(date_to)):
        qs = qs.filter(accepted_at__lt=_next_day_start(_clean(date_to)))

    return qs.order_by("-created_at")


# ---------------------------------------------------------------------------
# Profit breakdown (total_invoice_revenue/cogs/total_gross_profit drill-down)
# ---------------------------------------------------------------------------

def get_profit_breakdown(
    *,
    customer_name : str = None,
    customer_code : str = None,
    date_from     : str = None,
    date_to       : str = None,
) -> QuerySet:
    """
    Full breakdown of confirmed invoices' revenue/COGS/profit
    (total_invoice_revenue / total_invoice_cogs / total_gross_profit drill-down).
    """
    from billing.models import Invoice

    qs = Invoice.objects.filter(
        is_deleted=False, is_data_entry=False,
    ).exclude(status=Invoice.Status.DRAFT).select_related("customer")

    if _clean(customer_name):
        qs = qs.filter(search_q(_clean(customer_name), "customer__name"))
    if _clean(customer_code):
        qs = qs.filter(search_q(_clean(customer_code), "customer__code"))
    if _clean(date_from) and _day_start(_clean(date_from)):
        qs = qs.filter(confirmed_at__gte=_day_start(_clean(date_from)))
    if _clean(date_to) and _next_day_start(_clean(date_to)):
        qs = qs.filter(confirmed_at__lt=_next_day_start(_clean(date_to)))

    return qs.order_by("-created_at")


# ---------------------------------------------------------------------------
# Gross profit trend (dashboard graph)
# ---------------------------------------------------------------------------

def _add_months(year: int, month: int, delta: int) -> tuple:
    """Month-only arithmetic, no external date libraries needed."""
    total = (year * 12 + (month - 1)) + delta
    return total // 12, (total % 12) + 1


def get_gross_profit_trend(*, date_from: str = None, date_to: str = None) -> list:
    """
    Revenue/COGS/gross profit grouped by month — powers the dashboard graph.
    Defaults to the last 6 months (inclusive of the current month) when no
    range is given; otherwise honors the caller's date_from/date_to.

    Scales to any date range (3-5+ years) because the query result size is
    bounded by the number of MONTHS in range, not the number of invoices —
    a 5-year range is at most 60 rows, computed by a single GROUP BY query
    backed by the index on Invoice.confirmed_at (see reports date-index work).
    Gaps (months with zero confirmed invoices) are filled with zeros in
    Python so the chart always renders a complete, contiguous series.
    """
    from billing.models import Invoice, Return
    from django.db.models.functions import TruncMonth
    from django.utils import timezone
    from datetime import date as date_cls

    from rest_framework.exceptions import ValidationError

    today = timezone.localtime(timezone.now()).date()

    date_from = _clean(date_from)
    date_to = _clean(date_to)

    def _parse(value, field_name):
        try:
            return date_cls.fromisoformat(value)
        except ValueError:
            raise ValidationError({field_name: f"'{value}' is not a valid date (expected YYYY-MM-DD)."})

    if not date_from and not date_to:
        # No filter at all — default window: last 6 months ending today.
        start_year, start_month = _add_months(today.year, today.month, -5)
        range_start = date_cls(start_year, start_month, 1)
        range_end = today
    elif date_from and not date_to:
        # Only a start given — bounded naturally by today, no cap risk.
        range_start = _parse(date_from, "date_from")
        range_end = today
    elif date_to and not date_from:
        # Only an end given — mirror the "6 months" default, anchored at
        # date_to instead of today. Previously defaulted range_start to
        # 2000-01-01, which combined with the range-size cap below made
        # every date_to-only request fail validation.
        range_end = _parse(date_to, "date_to")
        start_year, start_month = _add_months(range_end.year, range_end.month, -5)
        range_start = date_cls(start_year, start_month, 1)
    else:
        range_start = _parse(date_from, "date_from")
        range_end = _parse(date_to, "date_to")

    if range_start > range_end:
        raise ValidationError({"date_from": "date_from cannot be after date_to."})

    # Bound the number of months a single request can generate — an
    # unreasonably wide range (e.g. a typo'd year) would otherwise iterate
    # the gap-filling loop below thousands of times for no useful chart.
    months_in_range = (range_end.year - range_start.year) * 12 + (range_end.month - range_start.month) + 1
    if months_in_range > 120:
        raise ValidationError({"date_from": "Date range cannot exceed 10 years (120 months)."})

    # Half-open datetime bounds instead of __date casts so the range can use
    # the confirmed_at index (same day-boundary helpers as everywhere else).
    qs = Invoice.objects.filter(
        is_deleted=False, is_data_entry=False,
    ).exclude(status=Invoice.Status.DRAFT).filter(
        confirmed_at__gte=_day_start(range_start),
        confirmed_at__lt=_next_day_start(range_end),
    )

    grouped = {
        row["month"].strftime("%Y-%m"): row
        for row in (
            qs.annotate(month=TruncMonth("confirmed_at"))
              .values("month")
              .annotate(
                  revenue     = Coalesce(Sum("grand_total"), Decimal("0")),
                  cogs        = Coalesce(Sum("total_cogs"), Decimal("0")),
                  gross_profit = Coalesce(Sum("gross_profit"), Decimal("0")),
              )
        )
    }

    # Returns ACCEPTED within this range, grouped by their own month — same
    # "recognize when it happens" treatment as get_profit_margin_report_stats.
    # A return accepted in month M can belong to a sale confirmed in an
    # earlier month (outside this grouping entirely) — that's fine, it still
    # correctly reduces month M's net figures.
    return_qs = Return.objects.filter(
        is_deleted=False, status=Return.Status.ACCEPTED,
        accepted_at__gte=_day_start(range_start),
        accepted_at__lt=_next_day_start(range_end),
    )
    returns_grouped = {
        row["month"].strftime("%Y-%m"): row
        for row in (
            return_qs.annotate(month=TruncMonth("accepted_at"))
                      .values("month")
                      .annotate(
                          return_value = Coalesce(Sum("total_return_amount"), Decimal("0")),
                          return_cogs  = Coalesce(Sum("total_return_cogs"), Decimal("0")),
                      )
        )
    }

    # Fill every month in [range_start, range_end], even ones with no data.
    result = []
    year, month = range_start.year, range_start.month
    end_key = range_end.strftime("%Y-%m")
    while True:
        key = f"{year:04d}-{month:02d}"
        row = grouped.get(key)
        return_row = returns_grouped.get(key)

        revenue      = row["revenue"] if row else Decimal("0")
        cogs         = row["cogs"] if row else Decimal("0")
        gross_profit = row["gross_profit"] if row else Decimal("0")
        return_value = return_row["return_value"] if return_row else Decimal("0")
        return_cogs  = return_row["return_cogs"] if return_row else Decimal("0")

        # Not floored — a month with heavy returns and little new revenue can
        # legitimately show a negative net figure. See get_profit_margin_report_stats.
        net_revenue      = revenue - return_value
        net_cogs         = cogs - return_cogs
        net_gross_profit = net_revenue - net_cogs

        result.append({
            "month"            : key,
            "revenue"          : revenue,
            "cogs"             : cogs,
            "gross_profit"     : gross_profit,
            "net_revenue"      : net_revenue,
            "net_cogs"         : net_cogs,
            "net_gross_profit" : net_gross_profit,
        })
        if key >= end_key:
            break
        year, month = _add_months(year, month, 1)

    return result


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _clean(value):
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped if stripped else None