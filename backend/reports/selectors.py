from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, QuerySet, Sum
from django.db.models.functions import Coalesce

from backend.search import search_q
from billing.models import Invoice, Payment, Return
from cash_flow.models import CashFlow, Expense
# Shared index-friendly day-boundary helpers (aware datetimes at local
# midnight) — same ones billing/ledger/cash_flow use for datetime-column
# date filters.
from purchases.selectors import _day_start, _next_day_start
from purchases.models import Inventory, LostInventoryItem, PurchaseItem, PurchaseOrder, PurchaseReturn


def _clean(value):
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _apply_datetime_range_filter(qs, *, field: str, date: str = None, date_from: str = None, date_to: str = None) -> QuerySet:
    """
    Half-open [start, next-day) bounds on a DateTimeField column instead of
    the index-defeating `__date` cast — matches exactly the same local
    calendar day (settings.TIME_ZONE) the old cast selected, but keeps the
    column's index usable. `date` narrows to that single day.
    """
    if _clean(date):
        d = _clean(date)
        return qs.filter(**{f"{field}__gte": _day_start(d), f"{field}__lt": _next_day_start(d)})
    if _clean(date_from):
        start = _day_start(_clean(date_from))
        if start:
            qs = qs.filter(**{f"{field}__gte": start})
    if _clean(date_to):
        end = _next_day_start(_clean(date_to))
        if end:
            qs = qs.filter(**{f"{field}__lt": end})
    return qs


# ---------------------------------------------------------------------------
# Invoices report
# ---------------------------------------------------------------------------

def get_invoices_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    Non-draft invoices (confirmed/partial/returned — all real, finalized
    invoices), filtered by their confirmed_at date. `__date` lookups are
    evaluated in settings.TIME_ZONE (Asia/Karachi), so this already matches
    the local calendar day shown in the UI.
    """
    qs = Invoice.objects.filter(is_deleted=False, is_data_entry=False).exclude(
        status=Invoice.Status.DRAFT,
    ).select_related("customer").order_by("-confirmed_at")

    return _apply_datetime_range_filter(qs, field="confirmed_at", date=date, date_from=date_from, date_to=date_to)


def get_invoices_report_stats(queryset: QuerySet) -> dict:
    return queryset.aggregate(
        total_invoices     = Count("id"),
        total_invoices_cash = Coalesce(Sum("grand_total"), Decimal("0")),
    )


def get_invoices_report_stats_all_time() -> dict:
    """
    No-filter case — reads the pre-synced CashFlow total instead of scanning
    the full invoice history. Count stays a live .count() (cheap regardless
    of table size, same reasoning already applied to the dashboard's
    total_number_of_invoices).
    """
    cf = CashFlow.get_instance()
    return {
        "total_invoices": Invoice.objects.filter(
            is_deleted=False, is_data_entry=False,
        ).exclude(status=Invoice.Status.DRAFT).count(),
        "total_invoices_cash": cf.total_invoice_revenue,
    }


# ---------------------------------------------------------------------------
# Cash collected report
# ---------------------------------------------------------------------------

def get_cash_collected_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    All payment collections (any method) — money that actually came in.
    Filtered by payment_date.
    """
    qs = Payment.objects.filter(
        is_deleted=False, amount__gt=0,
    ).select_related("invoice__customer").order_by("-payment_date")

    if _clean(date):
        qs = qs.filter(payment_date=_clean(date))
    if _clean(date_from):
        qs = qs.filter(payment_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(payment_date__lte=_clean(date_to))

    return qs


def get_cash_collected_report_stats(queryset: QuerySet) -> dict:
    return queryset.aggregate(
        total_payments        = Count("id"),
        total_cash_collected  = Coalesce(Sum("amount"), Decimal("0")),
    )


def get_cash_collected_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced CashFlow total (payments received)."""
    cf = CashFlow.get_instance()
    return {
        "total_payments": Payment.objects.filter(is_deleted=False, amount__gt=0).count(),
        "total_cash_collected": cf.total_invoices_cash,
    }


# ---------------------------------------------------------------------------
# Expenses report
# ---------------------------------------------------------------------------

def get_expenses_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    All non-deleted expenses, filtered by expense_date.
    """
    qs = Expense.objects.filter(is_deleted=False).select_related("category").order_by("-expense_date")

    if _clean(date):
        qs = qs.filter(expense_date=_clean(date))
    if _clean(date_from):
        qs = qs.filter(expense_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(expense_date__lte=_clean(date_to))

    return qs


def get_expenses_report_stats(queryset: QuerySet) -> dict:
    return queryset.aggregate(
        total_expenses      = Count("id"),
        total_expenses_cash = Coalesce(Sum("amount"), Decimal("0")),
    )


def get_expenses_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced CashFlow total."""
    cf = CashFlow.get_instance()
    return {
        "total_expenses": Expense.objects.filter(is_deleted=False).count(),
        "total_expenses_cash": cf.total_expenses_amount,
    }


# ---------------------------------------------------------------------------
# Lost inventory report
# ---------------------------------------------------------------------------

def get_lost_inventory_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    Every product lost in a batch (LostInventoryItem), flattened to one row
    per product per batch. Filtered by the parent record's created_at date —
    LostInventoryItem itself has no date field.
    """
    qs = LostInventoryItem.objects.filter(record__is_deleted=False).select_related(
        "record", "product",
    ).order_by("-record__created_at")

    return _apply_datetime_range_filter(
        qs, field="record__created_at", date=date, date_from=date_from, date_to=date_to,
    )


def get_lost_inventory_report_stats(queryset: QuerySet) -> dict:
    agg = queryset.aggregate(
        total_lost_items      = Count("id"),
        total_lost_cash       = Coalesce(Sum("total_cost"), Decimal("0")),
        total_recovered_cash  = Coalesce(
            Sum(F("unit_cost") * F("found_quantity")), Decimal("0"),
            output_field=DecimalField(max_digits=18, decimal_places=4),
        ),
    )
    agg["net_lost_cash"] = agg["total_lost_cash"] - agg["total_recovered_cash"]
    return agg


def get_lost_inventory_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced CashFlow totals (instant at any scale)."""
    cf = CashFlow.get_instance()
    total_lost      = cf.total_lost_inventory_worth
    total_recovered = cf.total_lost_inventory_recovered
    return {
        "total_lost_items"    : LostInventoryItem.objects.filter(record__is_deleted=False).count(),
        "total_lost_cash"     : total_lost,
        "total_recovered_cash": total_recovered,
        "net_lost_cash"       : total_lost - total_recovered,
    }


# ---------------------------------------------------------------------------
# Purchase returns report
# ---------------------------------------------------------------------------

def get_purchase_returns_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    Accepted returns to suppliers, filtered by accepted_at. Pending returns
    are excluded — their financial fields are still 0 until acceptance.
    """
    qs = PurchaseReturn.objects.filter(
        is_deleted=False, status=PurchaseReturn.Status.ACCEPTED,
    ).select_related("order__supplier").order_by("-accepted_at")

    return _apply_datetime_range_filter(qs, field="accepted_at", date=date, date_from=date_from, date_to=date_to)


def get_purchase_returns_report_stats(queryset: QuerySet) -> dict:
    return queryset.aggregate(
        total_returns      = Count("id"),
        total_return_value = Coalesce(Sum("total_return_amount"), Decimal("0")),
        total_return_cogs  = Coalesce(Sum("total_return_gross"), Decimal("0")),
    )


def get_purchase_returns_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced CashFlow totals."""
    cf = CashFlow.get_instance()
    return {
        "total_returns": PurchaseReturn.objects.filter(
            is_deleted=False, status=PurchaseReturn.Status.ACCEPTED,
        ).count(),
        "total_return_value": cf.total_purchase_returns_value,
        "total_return_cogs": cf.total_purchase_returns_cogs,
    }


# ---------------------------------------------------------------------------
# Customer returns report
# ---------------------------------------------------------------------------

def get_customer_returns_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    Accepted returns from customers, filtered by accepted_at. Pending returns
    are excluded — their financial fields are still 0 until acceptance.
    """
    qs = Return.objects.filter(
        is_deleted=False, status=Return.Status.ACCEPTED,
    ).select_related("invoice__customer").order_by("-accepted_at")

    return _apply_datetime_range_filter(qs, field="accepted_at", date=date, date_from=date_from, date_to=date_to)


def get_customer_returns_report_stats(queryset: QuerySet) -> dict:
    return queryset.aggregate(
        total_returns      = Count("id"),
        total_return_value = Coalesce(Sum("total_return_amount"), Decimal("0")),
        total_return_cogs  = Coalesce(Sum("total_return_cogs"), Decimal("0")),
    )


def get_customer_returns_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced CashFlow totals."""
    cf = CashFlow.get_instance()
    return {
        "total_returns": Return.objects.filter(
            is_deleted=False, status=Return.Status.ACCEPTED,
        ).count(),
        "total_return_value": cf.total_customer_returns_value,
        "total_return_cogs": cf.total_customer_returns_cogs,
    }


# ---------------------------------------------------------------------------
# Profit / margin report
# ---------------------------------------------------------------------------

def get_profit_margin_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    Non-draft invoices, filtered by confirmed_at. grand_total/total_cogs/
    gross_profit are stored per invoice, but NOT reduced by later returns —
    _recalculate_invoice_totals sums each item's ORIGINAL line_total/line_cogs
    regardless of returned_quantity, so these stay the historical "as sold"
    figures forever. get_profit_margin_report_stats() computes the net-of-
    returns figures separately, by subtracting accepted returns in the same
    date window — see that function's docstring.
    """
    qs = Invoice.objects.filter(is_deleted=False, is_data_entry=False).exclude(
        status=Invoice.Status.DRAFT,
    ).select_related("customer").order_by("-confirmed_at")

    return _apply_datetime_range_filter(qs, field="confirmed_at", date=date, date_from=date_from, date_to=date_to)


def get_profit_margin_report_stats(
    queryset: QuerySet, *, date: str = None, date_from: str = None, date_to: str = None,
) -> dict:
    """
    Gross figures sum the filtered invoices directly (unaffected by returns,
    see get_profit_margin_report_queryset). Net figures additionally subtract
    every return ACCEPTED within the same date window — regardless of which
    invoice/period the original sale belongs to, matching how every other
    event in this app is recognized (at the moment it happens, not
    retroactively reallocated to an earlier period).
    """
    invoice_totals = queryset.aggregate(
        total_invoices     = Count("id"),
        total_revenue      = Coalesce(Sum("grand_total"), Decimal("0")),
        total_cogs         = Coalesce(Sum("total_cogs"), Decimal("0")),
        total_gross_profit = Coalesce(Sum("gross_profit"), Decimal("0")),
    )

    return_totals = get_customer_returns_report_queryset(
        date=date, date_from=date_from, date_to=date_to,
    ).aggregate(
        total_return_value = Coalesce(Sum("total_return_amount"), Decimal("0")),
        total_return_cogs  = Coalesce(Sum("total_return_cogs"), Decimal("0")),
    )

    # Deliberately NOT floored at 0, unlike every other gross field in this
    # app — a return accepted in this window can belong to a sale from an
    # EARLIER window (outside this date filter), so a narrow window with
    # returns but little/no matching revenue can legitimately show negative
    # net revenue/COGS/profit. Flooring here would silently hide that a
    # window was a net loss, which defeats the entire point of this fix.
    net_revenue = invoice_totals["total_revenue"] - return_totals["total_return_value"]
    net_cogs    = invoice_totals["total_cogs"] - return_totals["total_return_cogs"]

    return {
        **invoice_totals,
        "net_revenue"      : net_revenue,
        "net_cogs"         : net_cogs,
        "net_gross_profit" : net_revenue - net_cogs,
    }


def get_profit_margin_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced CashFlow totals."""
    cf = CashFlow.get_instance()
    net_revenue = max(Decimal("0"), cf.total_invoice_revenue - cf.total_customer_returns_value)
    net_cogs    = max(Decimal("0"), cf.total_invoice_cogs - cf.total_customer_returns_cogs)
    return {
        "total_invoices": Invoice.objects.filter(
            is_deleted=False, is_data_entry=False,
        ).exclude(status=Invoice.Status.DRAFT).count(),
        "total_revenue": cf.total_invoice_revenue,
        "total_cogs": cf.total_invoice_cogs,
        "total_gross_profit": cf.total_gross_profit,
        "net_revenue": net_revenue,
        "net_cogs": net_cogs,
        "net_gross_profit": net_revenue - net_cogs,
    }


# ---------------------------------------------------------------------------
# Inventory valuation report — live snapshot, no date filtering
# ---------------------------------------------------------------------------

def get_inventory_valuation_report_data(*, search: str = None) -> list[dict]:
    """
    One row per product currently in stock, valued at FIFO cost from its
    remaining purchase batches. Point-in-time — no date filter applies.
    Mirrors the batch-walk math in purchases.selectors.get_fifo_cost_preview.

    Fetches every product's batches in ONE bulk query instead of one query
    per product (get_available_purchase_items_for_fifo called in a loop) —
    that N+1 pattern scaled with the size of the product catalog on every
    request; this is now 2 queries total regardless of catalog size.
    """
    inventory_qs = Inventory.objects.filter(quantity__gt=0).select_related(
        "product", "product__category",
    ).order_by("product__name")

    if _clean(search):
        inventory_qs = inventory_qs.filter(search_q(_clean(search), "product__name", "product__code"))

    inventories = list(inventory_qs)
    product_ids = [inv.product_id for inv in inventories]

    batches_by_product = {}
    batches = PurchaseItem.objects.filter(
        product_id__in=product_ids,
        is_deleted=False,
        order__status=PurchaseOrder.Status.CONFIRMED,
        remaining_quantity__gt=0,
    ).order_by("product_id", "order__confirmed_at")
    for batch in batches:
        batches_by_product.setdefault(batch.product_id, []).append(batch)

    rows = []
    for inv in inventories:
        total_value = Decimal("0")
        for batch in batches_by_product.get(inv.product_id, []):
            unit_cost = batch.total_price / batch.quantity if batch.quantity else batch.unit_price
            total_value += batch.remaining_quantity * unit_cost

        rows.append({
            "product_id": inv.product_id,
            "product_name": inv.product.name,
            "product_code": inv.product.code,
            "category_name": inv.product.category.name,
            "quantity_on_hand": inv.quantity,
            "avg_unit_cost": (total_value / inv.quantity) if inv.quantity else Decimal("0"),
            "total_value": total_value,
        })

    return rows


def get_inventory_valuation_report_stats(rows: list) -> dict:
    return {
        "total_products":         len(rows),
        "total_quantity_on_hand": sum((r["quantity_on_hand"] for r in rows), 0),
        "total_inventory_value":  sum((r["total_value"] for r in rows), Decimal("0")),
    }


# ---------------------------------------------------------------------------
# Sales Tax report — Input Tax (purchases) side
# ---------------------------------------------------------------------------

def get_input_tax_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    Confirmed, non-data-entry purchase orders, filtered by confirmed_at.
    gst_total/wht_total are already stored per order (same numbers taxes.
    services.sync_purchase_tax uses), so no per-item aggregation is needed.
    """
    qs = PurchaseOrder.objects.filter(
        is_deleted=False, is_data_entry=False, status="confirmed",
    ).select_related("supplier").order_by("-confirmed_at")

    return _apply_datetime_range_filter(qs, field="confirmed_at", date=date, date_from=date_from, date_to=date_to)


def get_input_tax_report_stats(queryset: QuerySet) -> dict:
    agg = queryset.aggregate(
        total_orders          = Count("id"),
        total_input_tax_paid  = Coalesce(Sum("gst_total"), Decimal("0")),
        total_wht_withheld    = Coalesce(Sum("wht_total"), Decimal("0")),
    )
    return agg


def get_input_tax_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced TaxFlow totals."""
    from taxes.models import TaxFlow
    tf = TaxFlow.get_instance()
    return {
        "total_orders": PurchaseOrder.objects.filter(
            is_deleted=False, is_data_entry=False, status="confirmed",
        ).count(),
        "total_input_tax_paid": tf.total_input_tax_paid,
        "total_wht_withheld"  : tf.total_wht_withheld_from_suppliers,
    }


# ---------------------------------------------------------------------------
# Sales Tax report — Output Tax (invoices) side
# ---------------------------------------------------------------------------

def get_output_tax_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    Confirmed, non-data-entry, non-draft invoices, filtered by confirmed_at.
    gst_total/wht_total are already stored per invoice (same numbers taxes.
    services.sync_invoice_tax uses), so no per-item aggregation is needed.
    """
    qs = Invoice.objects.filter(is_deleted=False, is_data_entry=False).exclude(
        status=Invoice.Status.DRAFT,
    ).select_related("customer").order_by("-confirmed_at")

    return _apply_datetime_range_filter(qs, field="confirmed_at", date=date, date_from=date_from, date_to=date_to)


def get_output_tax_report_stats(queryset: QuerySet) -> dict:
    agg = queryset.aggregate(
        total_invoices              = Count("id"),
        total_output_tax_collected  = Coalesce(Sum("gst_total"), Decimal("0")),
        total_wht_withheld          = Coalesce(Sum("wht_total"), Decimal("0")),
    )
    return agg


def get_output_tax_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced TaxFlow totals."""
    from taxes.models import TaxFlow
    tf = TaxFlow.get_instance()
    return {
        "total_invoices": Invoice.objects.filter(
            is_deleted=False, is_data_entry=False,
        ).exclude(status=Invoice.Status.DRAFT).count(),
        "total_output_tax_collected": tf.total_output_tax_collected,
        "total_wht_withheld"        : tf.total_wht_withheld_by_customers,
    }


# ---------------------------------------------------------------------------
# Shared helper — translates YYYY-MM-DD date filters into YYYY-MM period
# bounds, for reports whose source model is keyed by a period string
# (MonthlyProfit, AssetValuationEntry) instead of a real date field.
# ---------------------------------------------------------------------------

def _period_bounds_from_dates(*, date: str = None, date_from: str = None, date_to: str = None) -> tuple:
    if _clean(date):
        p = _clean(date)[:7]
        return p, p
    lo = _clean(date_from)[:7] if _clean(date_from) else None
    hi = _clean(date_to)[:7] if _clean(date_to) else None
    return lo, hi


# ---------------------------------------------------------------------------
# Recurring expenses report
# ---------------------------------------------------------------------------

def get_recurring_expenses_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    Every recurring expense assignment — the underlying transactions behind
    the Monthly Breakdown page's per-period totals. Filtered by assigned_at,
    the date each due bill was actually posted.
    """
    from recurring_expenses.models import RecurringExpenseAssignment

    qs = RecurringExpenseAssignment.objects.filter(is_deleted=False).select_related(
        "category",
    ).order_by("-assigned_at")

    return _apply_datetime_range_filter(qs, field="assigned_at", date=date, date_from=date_from, date_to=date_to)


def get_recurring_expenses_report_stats(queryset: QuerySet) -> dict:
    agg = queryset.aggregate(
        total_assignments      = Count("id"),
        total_assigned_amount  = Coalesce(Sum("amount"), Decimal("0")),
        total_paid_amount      = Coalesce(Sum("amount_paid"), Decimal("0")),
    )
    agg["total_pending_amount"] = max(Decimal("0"), agg["total_assigned_amount"] - agg["total_paid_amount"])
    return agg


def get_recurring_expenses_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced RecurringExpenseFlow totals."""
    from recurring_expenses.models import RecurringExpenseAssignment, RecurringExpenseFlow

    ref = RecurringExpenseFlow.get_instance()
    return {
        "total_assignments"     : RecurringExpenseAssignment.objects.filter(is_deleted=False).count(),
        "total_assigned_amount" : ref.total_assigned_amount,
        "total_paid_amount"     : ref.total_paid_amount,
        "total_pending_amount"  : ref.total_pending_amount,
    }


# ---------------------------------------------------------------------------
# Net profit report — the real counterpart to Profit Margin Report
# ---------------------------------------------------------------------------

def get_net_profit_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    One row per FINALIZED month (profits.MonthlyProfit) — never the current,
    still-open month. Filtered by period, translated from the date/
    date_from/date_to query params (YYYY-MM-DD -> YYYY-MM) since
    MonthlyProfit is keyed by period, not a literal date field.
    """
    from profits.models import MonthlyProfit
    from profits.services import catch_up_monthly_profits

    catch_up_monthly_profits()

    qs = MonthlyProfit.objects.order_by("-period")
    lo, hi = _period_bounds_from_dates(date=date, date_from=date_from, date_to=date_to)
    if lo:
        qs = qs.filter(period__gte=lo)
    if hi:
        qs = qs.filter(period__lte=hi)
    return qs


def get_net_profit_report_stats(queryset: QuerySet) -> dict:
    return queryset.aggregate(
        total_months            = Count("id"),
        total_gross_profit      = Coalesce(Sum("gross_profit"), Decimal("0")),
        total_net_gross_profit  = Coalesce(Sum("net_gross_profit"), Decimal("0")),
        total_net_profit        = Coalesce(Sum("net_profit"), Decimal("0")),
        total_investor_share    = Coalesce(Sum("total_investor_share_amount"), Decimal("0")),
        total_owner_share       = Coalesce(Sum("owner_share_amount"), Decimal("0")),
    )


def get_net_profit_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced ProfitFlow totals, O(1)."""
    from profits.models import MonthlyProfit, ProfitFlow
    from profits.services import catch_up_monthly_profits

    catch_up_monthly_profits()
    pf = ProfitFlow.get_instance()
    return {
        "total_months"           : MonthlyProfit.objects.count(),
        "total_gross_profit"     : pf.total_gross_profit,
        "total_net_gross_profit" : pf.total_net_gross_profit,
        "total_net_profit"       : pf.total_net_profit,
        "total_investor_share"   : pf.total_investor_profit_share,
        "total_owner_share"      : pf.total_owner_profit_share,
    }


# ---------------------------------------------------------------------------
# Asset depreciation report
# ---------------------------------------------------------------------------

def get_asset_depreciation_report_queryset(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
) -> QuerySet:
    """
    One row per depreciation posting (assets.AssetValuationEntry,
    entry_type=depreciation) across every asset. Filtered by period,
    translated from date/date_from/date_to — the period the depreciation
    applies to, not the day it happened to be computed.
    """
    from assets.models import AssetValuationEntry
    from assets.selectors import get_asset_stats

    get_asset_stats()  # make sure catch-up has posted every due entry first

    qs = AssetValuationEntry.objects.filter(
        entry_type=AssetValuationEntry.EntryType.DEPRECIATION,
    ).select_related("asset", "asset__category").order_by("-period", "-created_at")

    lo, hi = _period_bounds_from_dates(date=date, date_from=date_from, date_to=date_to)
    if lo:
        qs = qs.filter(period__gte=lo)
    if hi:
        qs = qs.filter(period__lte=hi)
    return qs


def get_asset_depreciation_report_stats(queryset: QuerySet) -> dict:
    agg = queryset.aggregate(
        total_entries      = Count("id"),
        total_depreciation = Coalesce(Sum("amount"), Decimal("0")),
    )
    agg["total_depreciation"] = abs(agg["total_depreciation"])  # stored negative on each entry
    return agg


def get_asset_depreciation_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced AssetFlow total, O(1)."""
    from assets.models import AssetFlow, AssetValuationEntry
    from assets.selectors import get_asset_stats

    get_asset_stats()
    af = AssetFlow.get_instance()
    return {
        "total_entries"      : AssetValuationEntry.objects.filter(
            entry_type=AssetValuationEntry.EntryType.DEPRECIATION,
        ).count(),
        "total_depreciation" : af.total_accumulated_depreciation,
    }


# ---------------------------------------------------------------------------
# Stock Movement report — quantities only (purchased/purchase-returned/
# sold/sale-returned), per product and all-time. Unlike every other report
# above, there's no single source queryset — this groups across FOUR
# source tables (PurchaseItem, PurchaseReturnItem, InvoiceItem, ReturnItem),
# so it can't reuse the queryset/stats(queryset) pattern directly.
# ---------------------------------------------------------------------------

def _stock_movement_date_filter(qs, *, field: str, date: str = None, date_from: str = None, date_to: str = None) -> QuerySet:
    return _apply_datetime_range_filter(qs, field=field, date=date, date_from=date_from, date_to=date_to)


def _stock_movement_totals_by_product(
    *, date: str = None, date_from: str = None, date_to: str = None, search: str = None,
) -> dict:
    """
    {product_id: {"total_purchased": x, "total_purchase_returned": x,
    "total_sold": x, "total_sale_returned": x, "total_lost": x,
    "total_found": x}} for every product with ANY movement in the given
    window. Only called when a filter is actually applied — the no-filter
    case reads ProductStockMovement directly instead (O(1) per row, see
    get_stock_movement_report_rows).

    `search`, when given, narrows every one of the 6 source queries to only
    the matching products BEFORE aggregating (via an indexed `search_q`
    lookup on Product name/code, same trigram index the rows path already
    relies on) — so a search-scoped call stays fast and bounded by the
    (typically tiny) matching-product set, never by total table size, and
    "total X" in the response only ever sums the products actually shown.
    """
    zero = 0
    totals = {}

    product_ids = None
    if _clean(search):
        from purchases.models import Product
        product_ids = list(Product.objects.filter(search_q(_clean(search), "name", "code")).values_list("id", flat=True))
        if not product_ids:
            return {}

    def _add(product_id, field, amount):
        row = totals.setdefault(product_id, {
            "total_purchased": 0, "total_purchase_returned": 0,
            "total_sold": 0, "total_sale_returned": 0,
            "total_lost": 0, "total_found": 0,
        })
        row[field] += amount

    # NOT excluding order__is_data_entry here (unlike the sold/sale_returned
    # queries below) — a data-entry opening-stock order moves REAL physical
    # inventory (Inventory.quantity incremented, ProductStockMovement
    # updated via _adjust_stock_movement — see purchases.services.
    # create_opening_stock_order), so it must count as "purchased" here too,
    # exactly like the no-filter path (which reads ProductStockMovement
    # directly and already includes it). Excluding it here was the bug:
    # date-filtered totals silently dropped opening-stock purchases that
    # the unfiltered totals correctly showed.
    purchased_qs = PurchaseItem.objects.filter(
        is_deleted=False, order__is_deleted=False, order__status="confirmed",
    )
    if product_ids is not None:
        purchased_qs = purchased_qs.filter(product_id__in=product_ids)
    purchased_qs = _stock_movement_date_filter(
        purchased_qs, field="order__confirmed_at", date=date, date_from=date_from, date_to=date_to,
    )
    for row in purchased_qs.values("product_id").annotate(total=Coalesce(Sum("quantity"), zero)):
        _add(row["product_id"], "total_purchased", row["total"])

    from purchases.models import PurchaseReturnItem
    purchase_returned_qs = PurchaseReturnItem.objects.filter(
        return_record__is_deleted=False, return_record__status="accepted",
    )
    if product_ids is not None:
        purchase_returned_qs = purchase_returned_qs.filter(purchase_item__product_id__in=product_ids)
    purchase_returned_qs = _stock_movement_date_filter(
        purchase_returned_qs, field="return_record__accepted_at", date=date, date_from=date_from, date_to=date_to,
    )
    for row in purchase_returned_qs.values("purchase_item__product_id").annotate(total=Coalesce(Sum("quantity"), zero)):
        _add(row["purchase_item__product_id"], "total_purchase_returned", row["total"])

    from billing.models import InvoiceItem, ReturnItem
    sold_qs = InvoiceItem.objects.filter(
        invoice__is_deleted=False, invoice__is_data_entry=False,
    ).exclude(invoice__status="draft")
    if product_ids is not None:
        sold_qs = sold_qs.filter(product_id__in=product_ids)
    sold_qs = _stock_movement_date_filter(
        sold_qs, field="invoice__confirmed_at", date=date, date_from=date_from, date_to=date_to,
    )
    for row in sold_qs.values("product_id").annotate(total=Coalesce(Sum("quantity"), zero)):
        _add(row["product_id"], "total_sold", row["total"])

    sale_returned_qs = ReturnItem.objects.filter(
        return_record__is_deleted=False, return_record__status="accepted",
        invoice_item__invoice__is_data_entry=False,
    )
    if product_ids is not None:
        sale_returned_qs = sale_returned_qs.filter(invoice_item__product_id__in=product_ids)
    sale_returned_qs = _stock_movement_date_filter(
        sale_returned_qs, field="return_record__accepted_at", date=date, date_from=date_from, date_to=date_to,
    )
    for row in sale_returned_qs.values("invoice_item__product_id").annotate(total=Coalesce(Sum("quantity"), zero)):
        _add(row["invoice_item__product_id"], "total_sale_returned", row["total"])

    from purchases.models import LostInventoryItem, LostInventoryRecovery
    lost_qs = LostInventoryItem.objects.filter(record__is_deleted=False)
    if product_ids is not None:
        lost_qs = lost_qs.filter(product_id__in=product_ids)
    lost_qs = _stock_movement_date_filter(
        lost_qs, field="record__created_at", date=date, date_from=date_from, date_to=date_to,
    )
    for row in lost_qs.values("product_id").annotate(total=Coalesce(Sum("quantity"), zero)):
        _add(row["product_id"], "total_lost", row["total"])

    # recovered_at is a plain DateField (not DateTimeField) — no __date
    # transform needed/supported, unlike the other four *_date_filter calls.
    found_qs = LostInventoryRecovery.objects.all()
    if product_ids is not None:
        found_qs = found_qs.filter(lost_item__product_id__in=product_ids)
    if _clean(date):
        found_qs = found_qs.filter(recovered_at=_clean(date))
    if _clean(date_from):
        found_qs = found_qs.filter(recovered_at__gte=_clean(date_from))
    if _clean(date_to):
        found_qs = found_qs.filter(recovered_at__lte=_clean(date_to))
    for row in found_qs.values("lost_item__product_id").annotate(total=Coalesce(Sum("quantity"), zero)):
        _add(row["lost_item__product_id"], "total_found", row["total"])

    return totals


def get_stock_movement_report_stats(rows: list) -> dict:
    """
    Sums the SAME already-fetched row list the response returns — zero
    extra queries (matches get_inventory_valuation_report_stats's
    convention). Used to independently re-run the full 6-table aggregation
    a second time (once for rows, once for stats), which both doubled the
    query count AND could disagree with the row list's search scope —
    fixed by deriving stats from rows directly, so they can never diverge.
    """
    return _stock_movement_stats_from_totals({
        r["product_id"]: r for r in rows
    })


def get_stock_movement_report_stats_all_time() -> dict:
    """No-filter case — reads the pre-synced StockMovementFlow totals, O(1)."""
    from purchases.models import StockMovementFlow

    flow = StockMovementFlow.get_instance()
    return {
        "total_purchased"         : flow.total_purchased,
        "total_purchase_returned" : flow.total_purchase_returned,
        "total_sold"               : flow.total_sold,
        "total_sale_returned"      : flow.total_sale_returned,
        "total_lost"                : flow.total_lost,
        "total_found"               : flow.total_found,
    }


def get_stock_movement_report_rows(
    *,
    date      : str = None,
    date_from : str = None,
    date_to   : str = None,
    search    : str = None,
) -> list:
    """
    One row per product with at least one nonzero movement in scope.
    No filter -> reads ProductStockMovement directly (O(1) per row, bounded
    by today's product count — same exception Inventory Valuation uses).
    Any date filter -> live aggregation for that window (see above).
    `search` matches product name or code, applied either way.
    """
    from purchases.models import Product, ProductStockMovement

    has_date_filter = bool(_clean(date) or _clean(date_from) or _clean(date_to))

    if not has_date_filter:
        qs = ProductStockMovement.objects.select_related("product").filter(
            Q(total_purchased__gt=0) | Q(total_purchase_returned__gt=0) |
            Q(total_sold__gt=0) | Q(total_sale_returned__gt=0) |
            Q(total_lost__gt=0) | Q(total_found__gt=0)
        )
        if _clean(search):
            qs = qs.filter(search_q(_clean(search), "product__name", "product__code"))
        qs = qs.order_by("product__name")
        return [
            {
                "product_id"              : row.product_id,
                "product_name"            : row.product.name,
                "product_code"            : row.product.code,
                "total_purchased"         : row.total_purchased,
                "total_purchase_returned" : row.total_purchase_returned,
                "total_sold"               : row.total_sold,
                "total_sale_returned"      : row.total_sale_returned,
                "total_lost"               : row.total_lost,
                "total_found"              : row.total_found,
            }
            for row in qs
        ]

    totals = _stock_movement_totals_by_product(date=date, date_from=date_from, date_to=date_to, search=search)
    return _stock_movement_rows_from_totals(totals)


def _stock_movement_rows_from_totals(totals: dict) -> list:
    """Product name/code lookup for an already-computed totals dict — `totals`
    is expected to already be search-scoped (see _stock_movement_totals_by_product's
    `search` param), so this does no further filtering, just enrichment + ordering."""
    from purchases.models import Product

    if not totals:
        return []

    products = Product.objects.filter(id__in=totals.keys()).order_by("name")
    return [
        {
            "product_id"              : p.id,
            "product_name"            : p.name,
            "product_code"            : p.code,
            "total_purchased"         : totals[p.id]["total_purchased"],
            "total_purchase_returned" : totals[p.id]["total_purchase_returned"],
            "total_sold"               : totals[p.id]["total_sold"],
            "total_sale_returned"      : totals[p.id]["total_sale_returned"],
            "total_lost"               : totals[p.id]["total_lost"],
            "total_found"              : totals[p.id]["total_found"],
        }
        for p in products
    ]


def _stock_movement_stats_from_totals(totals: dict) -> dict:
    stats = {
        "total_purchased": 0, "total_purchase_returned": 0,
        "total_sold": 0, "total_sale_returned": 0,
        "total_lost": 0, "total_found": 0,
    }
    for row in totals.values():
        for key in stats:
            stats[key] += row[key]
    return stats


