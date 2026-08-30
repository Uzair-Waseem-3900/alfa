from calendar import monthrange
from datetime import date as date_cls, timedelta
from decimal import Decimal

from django.db.models import (
    Case, CharField, Count, DateField, Q, Subquery, Sum, Value, When,
)
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from billing.models import Invoice
from purchases.models import PurchaseOrder
from assets.models import Asset

# ---------------------------------------------------------------------------
# Aging buckets — shared by A/R and A/P aging
# ---------------------------------------------------------------------------
# "current" = not yet past due. Everything else buckets by how many days
# past due. Both reports are bounded to rows with a nonzero outstanding
# balance (never all invoice/order history) — the same "live snapshot
# report" exception architecture.md carves out for Inventory Valuation.

AGING_BUCKETS = ("current", "1_30", "31_60", "61_90", "over_90")


def _bucket_for_days_overdue(days_overdue: int) -> str:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1_30"
    if days_overdue <= 60:
        return "31_60"
    if days_overdue <= 90:
        return "61_90"
    return "over_90"


def _empty_bucket_totals() -> dict:
    return {bucket: {"count": 0, "total": 0} for bucket in AGING_BUCKETS}


def _bucket_case(due_field: str, today):
    """
    SQL equivalent of _bucket_for_days_overdue, expressed as DATE comparisons
    against `today` rather than as arithmetic on a day count.

    Why dates and not `today - due_date`: extracting an integer number of days
    from a date difference is not portable (Postgres yields an interval,
    SQLite needs julianday()), and Django would need a DurationField dance to
    make it work on both. Comparing the date column against precomputed
    threshold dates is plain, portable SQL, and it keeps the column directly
    comparable so an index on it can still be used.

    Boundary equivalence with the Python version, checked value by value:
        due == today      -> 0 days  -> current   (due >= today)
        due == today-1    -> 1       -> 1_30
        due == today-30   -> 30      -> 1_30      (>= today-30)
        due == today-31   -> 31      -> 31_60
        due == today-60   -> 60      -> 31_60
        due == today-61   -> 61      -> 61_90
        due == today-90   -> 90      -> 61_90
        due == today-91   -> 91      -> over_90
    """
    d30, d60, d90 = (today - timedelta(days=n) for n in (30, 60, 90))
    return Case(
        When(**{f"{due_field}__gte": today}, then=Value("current")),
        When(**{f"{due_field}__gte": d30}, then=Value("1_30")),
        When(**{f"{due_field}__gte": d60}, then=Value("31_60")),
        When(**{f"{due_field}__gte": d90}, then=Value("61_90")),
        default=Value("over_90"),
        output_field=CharField(),
    )


def _summary_from_queryset(qs, *, amount_field: str, count_key: str) -> dict:
    """
    Bucket totals via ONE GROUP BY instead of counting a materialized Python
    list. `qs` must be the UNFILTERED base queryset — the summary always
    describes the full outstanding set even when the table below it is
    narrowed to one bucket (the cards stay a stable reference point).
    """
    totals = _empty_bucket_totals()
    grand_total = Decimal("0")
    row_count = 0

    # .order_by() clears the queryset's row ordering (_due_date, id) before
    # grouping. Those columns are meaningless for a per-bucket total, and
    # leaving them on makes PostgreSQL reject the GROUP BY for referencing a
    # column that is neither grouped nor aggregated (SQLite allows it, so
    # this only shows up against real Postgres).
    for row in qs.order_by().values("_bucket").annotate(
        count=Count("id"), total=Sum(amount_field),
    ):
        bucket = totals[row["_bucket"]]
        amount = row["total"] or Decimal("0")
        bucket["count"] = row["count"]
        bucket["total"] = amount
        grand_total += amount
        row_count += row["count"]

    return {"buckets": totals, "grand_total": grand_total, count_key: row_count}


# ---------------------------------------------------------------------------
# A/R Aging — customers who owe us money, bucketed by invoice due date
# ---------------------------------------------------------------------------

def get_ar_aging_queryset(*, bucket: str = None):
    """
    Annotated QuerySet — NOT a list — so the DATABASE does the bucketing,
    the ordering and (once the view paginates it) the LIMIT/OFFSET.

    This used to build every outstanding invoice into a Python list, sort that
    list, and hand it to DRF's paginator, which then sliced 25 rows out of it.
    Serving page 1 therefore materialized the entire outstanding set. That set
    never self-limits: an invoice enters when it's confirmed with credit
    outstanding and only leaves when it's fully paid, and the over_90 bucket
    by definition never clears — so it was the one genuinely unbounded read in
    this app.

    Ordering: `_due_date` ASC is exactly the old `days_overdue` DESC, since
    days_overdue = today - due_date. `id` is a deterministic tiebreaker —
    without one, rows sharing a due date could repeat or vanish between pages,
    which the old single-materialized-list version couldn't suffer from but
    real LIMIT/OFFSET pagination absolutely can.

    Bounded to confirmed/partial invoices with credit_outstanding > 0 — see
    the idx_invoice_outstanding partial index.
    """
    today = timezone.localdate()
    qs = (
        Invoice.objects
        .filter(
            # is_data_entry invoices are INCLUDED on purpose. A customer
            # opening balance is a real receivable: create_opening_balance_invoice
            # writes a CONFIRMED invoice with credit_outstanding=amount and a
            # real payment_due_date, and it feeds CashFlow.customer_outstanding —
            # the very figure the Balance Sheet reports as Accounts Receivable.
            # Excluding them here meant this report could never reconcile with
            # the Balance Sheet, and money genuinely owed to the business was
            # missing from the collections list. billing's own docstring says it
            # outright: "opening balances are real carried-forward debt".
            #
            # Caveat worth knowing: these bucket by when the opening balance was
            # ENTERED (payment_due_date = entry date + 7), not when the debt
            # actually originated — no field records the original date. A long
            # overdue pre-go-live debt therefore shows as Current until that
            # window passes.
            status__in=[Invoice.Status.CONFIRMED, Invoice.Status.PARTIAL],
            credit_outstanding__gt=0,
        )
        .select_related("customer")
        .only(
            "id", "bill_number", "confirmed_at", "payment_due_date",
            "credit_outstanding", "customer_id", "customer__name", "customer__code",
        )
        .annotate(
            # Same fallback chain as the old Python expression. TruncDate
            # renders as AT TIME ZONE settings.TIME_ZONE under USE_TZ, which is
            # precisely what timezone.localtime(confirmed_at).date() computed.
            _due_date=Coalesce(
                "payment_due_date", TruncDate("confirmed_at"), Value(today),
                output_field=DateField(),
            ),
        )
        .annotate(_bucket=_bucket_case("_due_date", today))
    )
    if bucket:
        qs = qs.filter(_bucket=bucket)
    return qs.order_by("_due_date", "id")


def ar_aging_row(inv, today=None) -> dict:
    """One annotated Invoice -> the response dict. Called for the PAGE only
    (25 rows), so days_overdue staying a Python subtraction costs nothing and
    avoids non-portable date arithmetic in SQL."""
    today = today or timezone.localdate()
    return {
        "invoice_id": inv.id,
        "bill_number": inv.bill_number,
        "customer_id": inv.customer_id,
        "customer_name": inv.customer.name,
        "customer_code": inv.customer.code,
        "due_date": inv._due_date,
        "days_overdue": (today - inv._due_date).days,
        "bucket": inv._bucket,
        "outstanding": inv.credit_outstanding,
    }


def get_ar_aging_rows(*, bucket: str = None) -> list:
    """Every matching row as dicts — for the PDF print view (which genuinely
    needs the whole set) and for tests. The paginated list view goes through
    get_ar_aging_queryset instead and never materializes more than a page."""
    today = timezone.localdate()
    return [ar_aging_row(inv, today) for inv in get_ar_aging_queryset(bucket=bucket)]


def get_ar_aging_summary(rows: list = None) -> dict:
    """
    With `rows`: totals over exactly those dicts (used by the print view,
    which already holds the full set, and by tests).
    Without: ONE GROUP BY over the full outstanding set — no materialization.
    A test asserts the two paths agree, so they can't drift apart.
    """
    if rows is None:
        return _summary_from_queryset(
            get_ar_aging_queryset(), amount_field="credit_outstanding",
            count_key="invoice_count",
        )

    totals = _empty_bucket_totals()
    grand_total = 0
    for row in rows:
        bucket = totals[row["bucket"]]
        bucket["count"] += 1
        bucket["total"] += row["outstanding"]
        grand_total += row["outstanding"]
    return {"buckets": totals, "grand_total": grand_total, "invoice_count": len(rows)}


# ---------------------------------------------------------------------------
# A/P Aging — what we owe suppliers, bucketed by purchase-order age
# ---------------------------------------------------------------------------
# purchases.PurchaseOrder has no due-date field (suppliers here are paid on
# whatever informal terms exist, not a tracked due date) — so "overdue" is
# approximated by age since confirmation, same convention as this report
# would use for any supplier with no stated credit terms. Documented here
# rather than silently treated as equivalent to a real due date.

def get_ap_aging_queryset(*, bucket: str = None):
    """Annotated QuerySet, database-side bucketing/ordering/pagination — see
    get_ar_aging_queryset for the full reasoning. The only structural
    difference is that a PurchaseOrder has no due-date field, so age runs from
    confirmed_at alone."""
    today = timezone.localdate()
    qs = (
        PurchaseOrder.objects
        .filter(
            # is_data_entry orders are INCLUDED on purpose — see the matching
            # note in get_ar_aging_queryset. A supplier opening balance is a
            # real payable (create_opening_balance_order sets
            # payable_outstanding=amount and it feeds
            # CashFlow.supplier_payable_outstanding, which the Balance Sheet
            # reports as Accounts Payable).
            #
            # Opening STOCK orders are also is_data_entry, but they are NOT
            # payables — create_opening_stock_order never calls
            # _sync_order_payable, so payable_outstanding stays 0 and the
            # `> 0` filter below already excludes them. That is why no
            # is_data_entry test is needed to keep them out.
            status=PurchaseOrder.Status.CONFIRMED,
            payable_outstanding__gt=0,
        )
        .select_related("supplier")
        .only(
            "id", "order_number", "confirmed_at",
            "payable_outstanding", "supplier_id", "supplier__name", "supplier__code",
        )
        .annotate(
            _due_date=Coalesce(
                TruncDate("confirmed_at"), Value(today), output_field=DateField(),
            ),
        )
        .annotate(_bucket=_bucket_case("_due_date", today))
    )
    if bucket:
        qs = qs.filter(_bucket=bucket)
    return qs.order_by("_due_date", "id")


def ap_aging_row(order, today=None) -> dict:
    today = today or timezone.localdate()
    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "supplier_id": order.supplier_id,
        "supplier_name": order.supplier.name,
        "supplier_code": order.supplier.code,
        "confirmed_date": order._due_date,
        "days_overdue": (today - order._due_date).days,
        "bucket": order._bucket,
        "outstanding": order.payable_outstanding,
    }


def get_ap_aging_rows(*, bucket: str = None) -> list:
    today = timezone.localdate()
    return [ap_aging_row(o, today) for o in get_ap_aging_queryset(bucket=bucket)]


def get_ap_aging_summary(rows: list = None) -> dict:
    """See get_ar_aging_summary — same two paths, same drift-guard test."""
    if rows is None:
        return _summary_from_queryset(
            get_ap_aging_queryset(), amount_field="payable_outstanding",
            count_key="order_count",
        )

    totals = _empty_bucket_totals()
    grand_total = 0
    for row in rows:
        bucket = totals[row["bucket"]]
        bucket["count"] += 1
        bucket["total"] += row["outstanding"]
        grand_total += row["outstanding"]
    return {"buckets": totals, "grand_total": grand_total, "order_count": len(rows)}


# ---------------------------------------------------------------------------
# Fixed Asset Register
# ---------------------------------------------------------------------------
# Reads only already-stored O(1) fields (Asset.cost/current_worth) — no
# AssetValuationEntry aggregation needed, accumulated depreciation is just
# cost - current_worth for depreciation-method assets.

def get_fixed_asset_register_rows(*, include_disposed: bool = False) -> list:
    # Depreciation/growth for the current period is posted by the assets
    # catch-up, not on write — so reading Asset.current_worth WITHOUT
    # triggering that catch-up first can show a net book value that is one
    # period stale. reports.selectors.get_asset_depreciation_report_queryset
    # already calls this for exactly that reason; this register did not, so
    # the two pages could show DIFFERENT net book values for the same asset
    # and both look authoritative.
    #
    # Cheap: get_asset_stats() is marker-gated on
    # AssetFlow.depreciation_caught_up_through (architecture.md's O(1)
    # catch-up rule), so once the period is already posted this is a single
    # singleton read, not a per-asset sweep.
    from assets.selectors import get_asset_stats

    get_asset_stats()

    qs = (
        Asset.objects
        .filter(is_deleted=False)
        .select_related("category", "disposal")
    )
    if not include_disposed:
        qs = qs.filter(is_disposed=False)

    rows = []
    for asset in qs:
        accumulated_depreciation = (
            asset.cost - asset.current_worth
            if asset.category.valuation_method == asset.category.ValuationMethod.DEPRECIATION
            else 0
        )
        disposal = getattr(asset, "disposal", None)
        rows.append({
            "asset_id": asset.id,
            "name": asset.name,
            "category": asset.category.name,
            "valuation_method": asset.category.valuation_method,
            "acquisition_date": asset.acquisition_date,
            "cost": asset.cost,
            "accumulated_depreciation": accumulated_depreciation,
            "net_book_value": asset.current_worth,
            "is_disposed": asset.is_disposed,
            "disposal_date": disposal.disposal_date if disposal else None,
            "disposal_type": disposal.disposal_type if disposal else None,
            "gain_loss_on_disposal": disposal.gain_loss if disposal else None,
        })
    return rows


def get_fixed_asset_register_summary(rows: list = None) -> dict:
    rows = get_fixed_asset_register_rows() if rows is None else rows
    return {
        "asset_count": len(rows),
        "total_cost": sum((r["cost"] for r in rows), 0),
        "total_accumulated_depreciation": sum((r["accumulated_depreciation"] for r in rows), 0),
        "total_net_book_value": sum((r["net_book_value"] for r in rows), 0),
    }


# ---------------------------------------------------------------------------
# Cash Flow Statement — classifies cash_flow.CashMovement into the standard
# Operating / Investing / Financing activities, aggregated over a date range.
# ---------------------------------------------------------------------------
# opening_cash is a one-time data-entry bootstrap event (the pre-existing
# balance registered at go-live) — not a real activity within any reporting
# period, so it's excluded from all three buckets rather than force-fit into
# one.

OPERATING_MOVEMENT_TYPES = {
    "invoice_payment", "advance_payment", "expense", "supplier_payment",
    "tax_payment", "wht_payment", "cash_lost", "cash_found",
    "recurring_expense_payment",
}
INVESTING_MOVEMENT_TYPES = {"asset_purchase", "asset_sold"}
FINANCING_MOVEMENT_TYPES = {
    "investor_investment", "investor_withdrawal", "owner_contribution",
    "owner_drawing", "investor_profit_payout", "owner_profit_payout",
}

_BUCKET_BY_MOVEMENT_TYPE = {
    **{mt: "operating" for mt in OPERATING_MOVEMENT_TYPES},
    **{mt: "investing" for mt in INVESTING_MOVEMENT_TYPES},
    **{mt: "financing" for mt in FINANCING_MOVEMENT_TYPES},
}

_MOVEMENT_TYPE_LABELS = {
    "invoice_payment": "Invoice Payments Received",
    "advance_payment": "Advance Payments",
    "expense": "Expenses Paid",
    "supplier_payment": "Supplier Payments",
    "tax_payment": "GST Payments to FBR",
    "wht_payment": "WHT Payments to FBR",
    "cash_lost": "Cash Lost",
    "cash_found": "Cash Found",
    "recurring_expense_payment": "Recurring Expense Payments",
    "asset_purchase": "Fixed Asset Purchases",
    "asset_sold": "Fixed Asset Sale Proceeds",
    "investor_investment": "Investor Contributions",
    "investor_withdrawal": "Investor Withdrawals",
    "owner_contribution": "Owner Contributions",
    "owner_drawing": "Owner Drawings",
    "investor_profit_payout": "Investor Profit Payouts",
    "owner_profit_payout": "Owner Profit Payouts",
}


def get_cash_flow_statement(*, date_from: str, date_to: str) -> dict:
    """
    One indexed GROUP BY query (movement_type, direction) over CashMovement's
    date range — never a per-row Python merge. Opening/closing cash balance
    is only included when date_to is today: closing = CashFlow.cash_in_hand
    (already O(1)), opening = closing - net_change. For any range that ends
    in the past, computing an opening balance would mean summing all
    CashMovement history before the range started — unbounded, so it's
    simply omitted rather than silently shipped as an O(n) query.
    """
    from rest_framework.exceptions import ValidationError

    from cash_flow.models import CashFlow, CashMovement

    # Validate/cap BEFORE querying — these two values arrive straight from the
    # query string. Previously neither was parsed nor bounded, so
    # ?date_from=1900-01-01 sequentially scanned the whole CashMovement table
    # (the fastest-growing table in the project) and a malformed date reached
    # the ORM and surfaced as a 500. An inverted range was worse than either:
    # it returned an empty statement with no error at all, which looks like a
    # real answer.
    #
    # Same guard shape and same 120-month ceiling as
    # cash_flow.selectors.get_gross_profit_trend, which already bounds this
    # exact class of request.
    def _parse(value, field_name):
        try:
            return date_cls.fromisoformat(str(value))
        except ValueError:
            raise ValidationError(
                {field_name: f"'{value}' is not a valid date (expected YYYY-MM-DD)."}
            )

    range_start = _parse(date_from, "date_from")
    range_end = _parse(date_to, "date_to")

    if range_start > range_end:
        raise ValidationError({"date_from": "date_from cannot be after date_to."})

    months_in_range = (
        (range_end.year - range_start.year) * 12
        + (range_end.month - range_start.month) + 1
    )
    if months_in_range > 120:
        raise ValidationError({"date_from": "Date range cannot exceed 10 years (120 months)."})

    rows = (
        CashMovement.objects
        .filter(is_deleted=False, date__gte=range_start, date__lte=range_end)
        .exclude(movement_type="opening_cash")
        .values("movement_type", "direction")
        .annotate(total=Sum("amount"))
    )

    buckets = {"operating": [], "investing": [], "financing": []}
    bucket_totals = {"operating": Decimal("0"), "investing": Decimal("0"), "financing": Decimal("0")}
    for row in rows:
        movement_type = row["movement_type"]
        bucket = _BUCKET_BY_MOVEMENT_TYPE.get(movement_type)
        signed = row["total"] if row["direction"] == CashMovement.Direction.INFLOW else -row["total"]

        if bucket is None:
            # This used to `continue`, which SILENTLY dropped the movement —
            # and because net_change is summed from these buckets (and
            # opening_cash is then derived as closing - net_change), an
            # unmapped type didn't just go missing from a section, it made
            # BOTH totals quietly wrong with no error anywhere.
            #
            # Every movement type that exists today IS mapped, so this path
            # is currently unreachable. It exists because the bucket map is a
            # SIXTH place a new cash-touching feature has to be wired, and
            # instructions/cash-in-hand.md only lists five — so the next cash
            # feature that follows the documented process correctly would
            # still land here. Unclassified cash defaults to Operating (the
            # standard convention) so the totals stay honest, and the label
            # names the raw movement_type so the gap is visible on the
            # statement instead of invisible.
            bucket = "operating"
            label = f"Unclassified — {movement_type}"
        else:
            label = _MOVEMENT_TYPE_LABELS.get(movement_type, movement_type)

        buckets[bucket].append({"label": label, "amount": signed})
        bucket_totals[bucket] += signed

    net_change = bucket_totals["operating"] + bucket_totals["investing"] + bucket_totals["financing"]

    result = {
        "date_from": range_start.isoformat(),
        "date_to": range_end.isoformat(),
        "operating": {"lines": buckets["operating"], "net": bucket_totals["operating"]},
        "investing": {"lines": buckets["investing"], "net": bucket_totals["investing"]},
        "financing": {"lines": buckets["financing"], "net": bucket_totals["financing"]},
        "net_change_in_cash": net_change,
        "opening_cash": None,
        "closing_cash": None,
    }

    # Compare parsed dates, not strings — "2026-8-15" and "2026-08-15" are the
    # same day but only one of them ever matched the old string comparison,
    # silently omitting opening/closing cash for the other.
    if range_end == timezone.localdate():
        closing = CashFlow.get_instance().cash_in_hand
        result["closing_cash"] = closing
        result["opening_cash"] = closing - net_change

    return result


# ---------------------------------------------------------------------------
# Income Statement — reshapes profits.MonthlyProfit (finished months) or
# profits.selectors.get_current_month_profit() (current month, provisional)
# into standard statement layout, plus a per-category expense breakdown
# bounded to that one period.
# ---------------------------------------------------------------------------

def _period_bounds(period: str) -> tuple:
    year, month = int(period[:4]), int(period[5:7])
    first_day = date_cls(year, month, 1)
    last_day = date_cls(year, month, monthrange(year, month)[1])
    return first_day, last_day


def _get_expense_category_breakdown(period: str) -> list:
    """
    Category decomposition of `expenses_paid` ONLY — deliberately NOT of
    recurring expenses.

    This used to also concatenate one row per
    RecurringExpenseAssignmentPayment category, which broke the Income
    Statement's footing: the Operating Expenses section renders these
    breakdown lines AND a separate "Recurring Expenses" total line, so every
    recurring category was displayed twice while the bold "Total Operating
    Expenses" (computed from the source totals, not from these lines) stayed
    correct. The printed statement's own lines therefore did not add up to
    its own subtotal, overstated by exactly recurring_expenses_paid.

    The contract now is exact and asserted in tests: these rows sum to
    profits' `expenses_paid` for the same period, because this uses the same
    model, filter and date bounds as profits._compute_expenses_paid. Per
    category recurring detail lives on the Recurring Expenses page.

    Bounded to ONE month's Expense rows — never all history. expense_date is
    a plain DateField, already indexed.
    """
    from cash_flow.models import Expense

    first_day, last_day = _period_bounds(period)

    expense_rows = (
        Expense.objects
        .filter(is_deleted=False, expense_date__gte=first_day, expense_date__lte=last_day)
        .values("category__name")
        .annotate(total=Sum("amount"))
    )

    return [{"category": r["category__name"], "amount": r["total"]} for r in expense_rows]


def get_income_statement(*, period: str = None) -> dict:
    """
    period=None, or the current calendar month, returns the LIVE provisional
    figures (profits.get_current_month_profit) — never stored, always
    recomputed. Any other period reads the frozen profits.MonthlyProfit row
    for that period; raises MonthlyProfit.DoesNotExist if it was never
    finalized (same convention the Profits page already uses — the caller
    surfaces that as a 404, not a silent zero-filled statement).
    """
    from profits.models import MonthlyProfit
    from profits.selectors import get_current_month_net_profit_only

    today = timezone.localdate()
    current_period = f"{today.year:04d}-{today.month:02d}"

    if period is None or period == current_period:
        data = get_current_month_net_profit_only()
        resolved_period = current_period
    else:
        mp = MonthlyProfit.objects.get(period=period)
        data = {
            "period": mp.period,
            "is_provisional": False,
            "gross_revenue": mp.gross_revenue,
            "gross_cogs": mp.gross_cogs,
            "gross_profit": mp.gross_profit,
            "net_revenue": mp.net_revenue,
            "net_cogs": mp.net_cogs,
            "net_gross_profit": mp.net_gross_profit,
            "expenses_paid": mp.expenses_paid,
            "recurring_expenses_paid": mp.recurring_expenses_paid,
            "gst_paid": mp.gst_paid,
            "wht_paid": mp.wht_paid,
            "lost_cash": mp.lost_cash,
            "found_cash": mp.found_cash,
            "lost_inventory": mp.lost_inventory,
            "found_inventory": mp.found_inventory,
            "depreciation": mp.depreciation,
            "disposal_gain_loss": mp.disposal_gain_loss,
            "net_profit": mp.net_profit,
        }
        resolved_period = period

    data["expense_breakdown"] = _get_expense_category_breakdown(resolved_period)
    return data


# ---------------------------------------------------------------------------
# Balance Sheet
# ---------------------------------------------------------------------------
# "As of today" is live — every figure already lives in an O(1) singleton
# somewhere (CashFlow/AssetFlow/TaxFlow/CashManagementFlow/ProfitFlow),
# collapsed into ONE query via Subquery annotations instead of one round
# trip per singleton. Inventory value is the one exception (not a singleton
# — reuses the existing bounded Inventory Valuation query, 2 more queries).
# "As of a finished month" reads the frozen accounting.BalanceSheetSnapshot
# row for that period instead (see services.catch_up_balance_sheet_snapshots).

def _compute_equity_offsets() -> dict:
    """
    Net offset for go-live bootstrap data — sourced ENTIRELY from billing/
    purchases/cash_flow/cash_management, NEVER from data_entry.models. The
    data_entry app is a one-time bootstrap tool meant to be retired after
    go-live (per its own services.py docstrings, e.g. create_opening_stock:
    "Stored ... in cash_management ... so the record survives if this app
    is ever removed post-go-live") — every real bootstrap record already
    lives in the app it actually belongs to; data_entry.services only
    orchestrates writes to them. Importing data_entry.models here would
    make the ENTIRE Balance Sheet break the moment that app is removed, so
    this deliberately never does — verified by grepping for `is_data_entry`
    across the whole backend to enumerate every bootstrap path, not just
    the ones already known about.

    Five paths, each an asset OR liability/equity change with nothing
    offsetting it elsewhere — the first three were found by tracing a real
    Rs 1000 mismatch back to exactly this gap; the other two were added
    after being asked to specifically audit every data_entry edge case:
      + Customer Opening Balance    (billing.Invoice, receivable asset)
      + Opening Stock                (purchases.PurchaseOrder, inventory asset)
      + Opening Cash                  (cash_flow.CashMovement, cash asset)
      - Supplier Opening Balance        (purchases.PurchaseOrder, payable liability)
      - Opening Investor Investment       (cash_management.InvestorTransaction —
        inflates CashManagementFlow.net_investor_capital, which feeds this
        Balance Sheet's investor_capital, with NO cash asset behind it BY
        DESIGN — cash_management.services.create_investor_transaction's
        is_data_entry branch deliberately skips the cash_in_hand sync,
        since "the cash isn't actually sitting in the till". Without
        subtracting this, a business that recorded pre-existing investor
        capital this way would show equity exceeding assets by exactly
        that amount.)

    Each PO/Invoice/transaction query filters is_deleted=False defensively
    even though these rows are described as "permanently locked after
    creation" in data_entry.services — cheap insurance, not load-bearing.

    ALSO returns the two ASSET-side offsets, which are a different class of
    problem but need the same treatment:
      + Pre-owned assets (acquisition_type='existing'), documented in
        assets/models.py as "already owned before being registered. No cash
        movement." — an asset from nothing, exactly like Opening Stock, and
        NOT go-live-only: it fires whenever anyone registers a pre-owned
        asset. Netted against depreciation posted for periods no income
        statement ever covered (an asset back-filled from a pre-go-live
        acquisition date has months with no MonthlyProfit row at all), so
        this line means "what that equipment was worth when tracking began".
      + Revaluation surplus. Only DEPRECIATION entries feed net profit, so a
        REVALUATION moves current_worth with nothing on the other side.

    ONE QUERY for all eight figures. They were six separate round-trips over
    six tables; at ~100ms each against Supabase that was ~600ms on every
    single live Balance Sheet load, to compute numbers that are constant
    after go-live. Each is now a correlated scalar subquery hung off the
    CashFlow singleton — the same pattern already proven by the five Flow
    reads above and by profits.compute_month_figures_in_one_query. The
    predicates are unchanged, so every figure is identical; only the number
    of round-trips moved.
    """
    from django.db.models import DecimalField, Exists, IntegerField, OuterRef, Value
    from django.db.models.functions import Coalesce

    from assets.models import Asset, AssetValuationEntry
    from billing.models import Invoice
    from cash_flow.models import CashFlow, CashMovement
    from cash_management.models import InvestorTransaction
    from profits.models import MonthlyProfit
    from purchases.models import PurchaseItem, PurchaseOrder

    zero = Decimal("0")
    money = DecimalField(max_digits=20, decimal_places=4)

    def scalar(qs, field, *, filter=None):
        """One-row scalar sum, safe on an empty table (a bare Subquery would
        return NULL)."""
        # .order_by() FIRST — clears Meta.ordering, which Django would
        # otherwise append to the SQL and leave referenced by the GROUP BY
        # without being grouped or aggregated. SQLite tolerates that;
        # PostgreSQL raises ProgrammingError. See the identical guard in
        # profits.services.compute_month_figures_in_one_query.
        grouped = (
            qs.order_by()
            .values(_g=Value(1, output_field=IntegerField()))
            .annotate(_t=Sum(field, filter=filter))
            .values("_t")[:1]
        )
        return Coalesce(Subquery(grouped, output_field=money),
                        Value(zero), output_field=money)

    has_items = PurchaseItem.objects.filter(order=OuterRef("pk"), is_deleted=False)
    data_entry_orders = PurchaseOrder.objects.filter(
        is_data_entry=True, is_deleted=False, status=PurchaseOrder.Status.CONFIRMED,
    )

    # Periods whose depreciation DID reach retained earnings: every finalized
    # MonthlyProfit plus the current month (recomputed live). Anything else
    # reduced current_worth without ever being expensed.
    today = timezone.localdate()
    current_period = f"{today.year:04d}-{today.month:02d}"
    expensed = Q(period__in=MonthlyProfit.objects.values("period")) | Q(period=current_period)

    def _read():
        return CashFlow.objects.filter(pk=1).annotate(
            _customer_ob=scalar(
                Invoice.objects.filter(is_data_entry=True, is_deleted=False),
                "grand_total"),
            # "Opening stock" POs have real line items; pure "opening balance"
            # POs never do — the same structural distinction, applied to both
            # sides. Two filtered sums over one base, not two scans.
            _opening_stock=scalar(
                data_entry_orders, "net_payable", filter=Exists(has_items)),
            _supplier_ob=scalar(
                data_entry_orders, "net_payable", filter=~Exists(has_items)),
            _opening_cash=scalar(
                CashMovement.objects.filter(
                    movement_type="opening_cash", is_deleted=False),
                "amount"),
            _investor_ob=scalar(
                InvestorTransaction.objects.filter(
                    is_data_entry=True, is_deleted=False,
                    transaction_type=InvestorTransaction.TransactionType.INVESTMENT),
                "amount"),
            _pre_owned_cost=scalar(
                Asset.objects.filter(
                    is_deleted=False,
                    acquisition_type=Asset.AcquisitionType.EXISTING),
                "cost"),
            _revaluation=scalar(
                AssetValuationEntry.objects.filter(asset__is_deleted=False),
                "amount",
                filter=Q(entry_type=AssetValuationEntry.EntryType.REVALUATION)),
            _unexpensed_dep=scalar(
                AssetValuationEntry.objects.filter(asset__is_deleted=False),
                "amount",
                filter=Q(entry_type=AssetValuationEntry.EntryType.DEPRECIATION)
                       & ~expensed),
        ).values(
            "_customer_ob", "_opening_stock", "_supplier_ob", "_opening_cash",
            "_investor_ob", "_pre_owned_cost", "_revaluation", "_unexpensed_dep",
        ).first()

    # Read first; only create the singleton if it genuinely doesn't exist yet.
    # Without the row, .filter(pk=1) returns nothing and EVERY figure would
    # silently read as zero — the same trap already documented in
    # get_balance_sheet_live.
    row = _read()
    if row is None:
        CashFlow.get_instance()
        row = _read()
    row = row or {}

    def g(key):
        return row.get(key) or zero

    return {
        "opening_balance_equity": (
            g("_customer_ob") + g("_opening_stock") + g("_opening_cash")
            - g("_supplier_ob") - g("_investor_ob")
        ),
        # `amount` is stored NEGATIVE for depreciation, so adding the
        # unexpensed sum reduces equity — no sign flip needed.
        "pre_owned_asset_equity": g("_pre_owned_cost") + g("_unexpensed_dep"),
        "asset_revaluation_surplus": g("_revaluation"),
    }


_STALE_SNAPSHOT_LAG_DAYS = 2


def _snapshot_freshness(*, period: str = None, computed_at=None) -> dict:
    """
    How late a frozen snapshot was actually taken, in days after the month it
    claims to describe.

    Why this has to be surfaced rather than fixed: every Balance Sheet figure
    is an ALL-TIME singleton that only knows "right now" — there is no stored
    history to reconstruct a true month-end position from. So
    catch_up_balance_sheet_snapshots can only copy whatever the singletons say
    at the moment it runs and stamp last month's label on it, and it is frozen
    once and never recomputed. Run it on the 1st and the snapshot is honest;
    run it on the 20th and "July" silently contains 20 days of August, with no
    way to detect that after the fact.

    lag_days makes that visible instead of silent. It does NOT make a late
    snapshot more accurate — nothing can, the information was never recorded —
    it just stops a late one from looking exactly as authoritative as a
    prompt one.

    Derived from the model's existing `computed_at` (auto_now_add), so no new
    column and no migration was needed, and every snapshot already frozen
    before this shipped reports its real lag too.

    Live ("as of today") sheets pass nothing and get is_snapshot=False — they
    read the singletons directly, so the concept simply doesn't apply.
    """
    if period is None or computed_at is None:
        return {
            "is_snapshot": False,
            "snapshot_taken_on": None,
            "lag_days": None,
            "is_stale": False,
        }

    # .localtime() first — computed_at is a UTC instant, and taking .date()
    # off it directly reads the UTC calendar day, which is the wrong day for
    # ~5 hours of every Pakistan day (see architecture.md).
    taken_on = timezone.localtime(computed_at).date()
    _, last_day = _period_bounds(period)
    lag_days = (taken_on - last_day).days

    return {
        "is_snapshot": True,
        "snapshot_taken_on": taken_on,
        "lag_days": lag_days,
        "is_stale": lag_days > _STALE_SNAPSHOT_LAG_DAYS,
    }


def _assemble_balance_sheet(*, cash_in_hand, accounts_receivable, accounts_payable,
                              inventory_value, fixed_assets_nbv, gst_payable,
                              wht_payable, owner_capital, investor_capital,
                              opening_balance_equity, retained_earnings,
                              pre_owned_asset_equity=Decimal("0"),
                              asset_revaluation_surplus=Decimal("0"),
                              freshness=None) -> dict:
    total_assets = cash_in_hand + accounts_receivable + inventory_value + fixed_assets_nbv
    total_liabilities = accounts_payable + gst_payable + wht_payable
    total_equity = (
        owner_capital + investor_capital + opening_balance_equity
        + pre_owned_asset_equity + asset_revaluation_surplus + retained_earnings
    )
    balance_check = total_assets - (total_liabilities + total_equity)

    return {
        "assets": {
            "cash_in_hand": cash_in_hand,
            "accounts_receivable": accounts_receivable,
            "inventory_value": inventory_value,
            "fixed_assets_nbv": fixed_assets_nbv,
            "total": total_assets,
        },
        "liabilities": {
            "accounts_payable": accounts_payable,
            "gst_payable": gst_payable,
            "wht_payable": wht_payable,
            "total": total_liabilities,
        },
        "equity": {
            "owner_capital": owner_capital,
            "investor_capital": investor_capital,
            "opening_balance_equity": opening_balance_equity,
            "pre_owned_asset_equity": pre_owned_asset_equity,
            "asset_revaluation_surplus": asset_revaluation_surplus,
            "retained_earnings": retained_earnings,
            "total": total_equity,
        },
        "balance_check": balance_check,
        "is_balanced": abs(balance_check) < Decimal("0.01"),
        "freshness": freshness or _snapshot_freshness(),
    }


def get_balance_sheet_live() -> dict:
    """
    ProfitFlow.total_net_profit only updates when a month is FINALIZED (the
    monthly catch-up), but inventory/receivables already move the instant an
    invoice is confirmed — so for the current, still-open month, Assets
    would silently outrun Equity by exactly that month's unrecognized
    profit if retained_earnings only counted finalized months. Adding
    get_current_month_profit()'s live provisional net_profit here (the same
    number the Profits page already shows) is what keeps this balanced —
    caught by the balance-check test itself before this fix, not assumed.
    """
    from cash_flow.models import CashFlow
    from assets.models import AssetFlow
    from taxes.models import TaxFlow
    from cash_management.models import CashManagementFlow
    from profits.models import ProfitFlow
    from profits.selectors import get_current_month_net_profit_only
    from reports.selectors import get_inventory_valuation_report_data, get_inventory_valuation_report_stats

    def _read_row():
        return (
            CashFlow.objects.filter(pk=1)
            .annotate(
            _fixed_assets_nbv=Subquery(AssetFlow.objects.filter(pk=1).values("total_current_worth")[:1]),
            _gst_payable=Subquery(TaxFlow.objects.filter(pk=1).values("sales_tax_outstanding")[:1]),
            _wht_payable=Subquery(TaxFlow.objects.filter(pk=1).values("wht_outstanding")[:1]),
            _owner_capital=Subquery(CashManagementFlow.objects.filter(pk=1).values("net_owner_capital")[:1]),
            _investor_capital=Subquery(CashManagementFlow.objects.filter(pk=1).values("net_investor_capital")[:1]),
            _total_net_profit=Subquery(ProfitFlow.objects.filter(pk=1).values("total_net_profit")[:1]),
            _total_paid_investors=Subquery(ProfitFlow.objects.filter(pk=1).values("total_paid_out_to_investors")[:1]),
            _total_paid_owner=Subquery(ProfitFlow.objects.filter(pk=1).values("total_paid_out_to_owner")[:1]),
            _total_reinvested_investors=Subquery(ProfitFlow.objects.filter(pk=1).values("total_reinvested_by_investors")[:1]),
                _total_reinvested_owner=Subquery(ProfitFlow.objects.filter(pk=1).values("total_reinvested_by_owner")[:1]),
            )
            .values(
                "cash_in_hand", "customer_outstanding", "supplier_payable_outstanding",
                "_fixed_assets_nbv", "_gst_payable", "_wht_payable",
                "_owner_capital", "_investor_capital", "_total_net_profit",
                "_total_paid_investors", "_total_paid_owner",
                "_total_reinvested_investors", "_total_reinvested_owner",
            )
            .first()
        )

    # Read FIRST, and only fall back to get_instance() if the singleton row
    # genuinely doesn't exist yet.
    #
    # The row must exist for this to be correct at all: a business that has
    # only ever used the Data Entry app's "Opening Investor Investment"
    # (which deliberately skips cash_in_hand — see
    # _compute_opening_balance_equity's docstring) never triggers CashFlow's
    # creation any other way, and a missing row would make `row` fall back to
    # {} so that EVERY field below — not just the cash ones — silently read
    # as zero. That was a real bug, caught by a test with only an investor
    # investment and nothing else.
    #
    # But calling get_instance() (a get_or_create SELECT) BEFORE the read
    # meant paying that extra round-trip on every single Balance Sheet load
    # forever, to guard a case that happens at most once in the system's
    # lifetime. Inverted: steady state is 1 query, and the bootstrap path
    # costs one extra query exactly once, ever.
    row = _read_row()
    if row is None:
        CashFlow.get_instance()
        row = _read_row()
    row = row or {}

    zero = Decimal("0")
    current_month_net_profit = get_current_month_net_profit_only()["net_profit"]
    retained_earnings = (
        (row.get("_total_net_profit") or zero)
        + current_month_net_profit
        - (row.get("_total_paid_investors") or zero)
        - (row.get("_total_paid_owner") or zero)
        - (row.get("_total_reinvested_investors") or zero)
        - (row.get("_total_reinvested_owner") or zero)
    )

    inventory_rows = get_inventory_valuation_report_data()
    inventory_value = get_inventory_valuation_report_stats(inventory_rows)["total_inventory_value"]

    return _assemble_balance_sheet(
        cash_in_hand=row.get("cash_in_hand") or zero,
        accounts_receivable=row.get("customer_outstanding") or zero,
        accounts_payable=row.get("supplier_payable_outstanding") or zero,
        inventory_value=inventory_value,
        fixed_assets_nbv=row.get("_fixed_assets_nbv") or zero,
        gst_payable=row.get("_gst_payable") or zero,
        wht_payable=row.get("_wht_payable") or zero,
        owner_capital=row.get("_owner_capital") or zero,
        investor_capital=row.get("_investor_capital") or zero,
        **_compute_equity_offsets(),
        retained_earnings=retained_earnings,
    )


def get_balance_sheet_for_period(period: str) -> dict:
    """Reads the frozen snapshot — raises BalanceSheetSnapshot.DoesNotExist
    if that month was never caught up (same convention as
    get_income_statement's MonthlyProfit lookup)."""
    from .models import BalanceSheetSnapshot

    snap = BalanceSheetSnapshot.objects.get(period=period)
    return _assemble_balance_sheet(
        cash_in_hand=snap.cash_in_hand,
        accounts_receivable=snap.accounts_receivable,
        accounts_payable=snap.accounts_payable,
        inventory_value=snap.inventory_value,
        fixed_assets_nbv=snap.fixed_assets_nbv,
        gst_payable=snap.gst_payable,
        wht_payable=snap.wht_payable,
        owner_capital=snap.owner_capital,
        investor_capital=snap.investor_capital,
        opening_balance_equity=snap.opening_balance_equity,
        pre_owned_asset_equity=snap.pre_owned_asset_equity,
        asset_revaluation_surplus=snap.asset_revaluation_surplus,
        retained_earnings=snap.retained_earnings,
        freshness=_snapshot_freshness(period=snap.period, computed_at=snap.computed_at),
    )
