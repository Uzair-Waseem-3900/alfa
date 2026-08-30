from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from reports.pdf_service import generate_report_pdf_bytes

from .pdf_service import generate_statement_pdf_bytes
from .permissions import IsAdminOrSuperuser
from .selectors import (
    ap_aging_row,
    ar_aging_row,
    get_ap_aging_queryset,
    get_ap_aging_rows,
    get_ap_aging_summary,
    get_ar_aging_queryset,
    get_ar_aging_rows,
    get_ar_aging_summary,
    get_balance_sheet_for_period,
    get_balance_sheet_live,
    get_cash_flow_statement,
    get_fixed_asset_register_rows,
    get_fixed_asset_register_summary,
    get_income_statement,
)
from .serializers import (
    APAgingRowSerializer,
    ARAgingRowSerializer,
    BalanceSheetSerializer,
    CashFlowStatementSerializer,
    FixedAssetRegisterRowSerializer,
    IncomeStatementSerializer,
)


def _fmt(value) -> str:
    return f"{Decimal(value):.2f}"


# PDF rendering is the slowest thing in this app by a wide margin, and it is
# NOT database-bound: the aging prints run a single query, then WeasyPrint
# takes roughly 30ms PER ROW to lay the table out, linearly, on top of a
# multi-second one-time warm-up. Measured on real data: 100 rows ~2.8s, 200
# rows ~7.7s, 383 rows ~11.4s. The aging reports are the only unbounded sets
# in this app (an invoice stays outstanding until it is paid, and the over_90
# bucket never clears), so at a few thousand rows this becomes minutes and a
# guaranteed gateway timeout.
#
# Deliberately generous — a real filtered view is far below it, so in normal
# use nothing is ever dropped.
MAX_PRINT_ROWS = 500


def _cap_print_rows(rows: list, *, noun: str) -> tuple:
    """
    Bounds a print set and reports the truncation LOUDLY.

    architecture.md's rule: no silent caps — a truncated report that doesn't
    say so reads as "this is everything", which on a financial document is
    worse than being slow. So the notice goes into the PDF's filter line
    (rendered directly under the title, impossible to miss) and the full
    unfiltered count stays visible in the stats block, which is sourced from
    the summary rather than from the truncated list.

    Returns (rows_to_render, notice_or_empty_string).
    """
    total = len(rows)
    if total <= MAX_PRINT_ROWS:
        return rows, ""

    return rows[:MAX_PRINT_ROWS], (
        f"  |  SHOWING FIRST {MAX_PRINT_ROWS} OF {total} {noun} — this report was "
        f"truncated to stay printable. Totals below still cover all {total}. "
        f"Narrow the filter to print the rest."
    )


# ---------------------------------------------------------------------------
# A/R Aging
# ---------------------------------------------------------------------------

class ARAgingListView(generics.ListAPIView):
    """
    GET /accounting/ar-aging/ — paginated, oldest-overdue-first.

    Response (paginated): {..., "summary": {"buckets": {...}, "grand_total":
    decimal, "invoice_count": int}, "results": [...]} — summary always
    reflects the FULL bounded result set (every outstanding invoice), same
    convention as reports.views's stats merging. Pass `?bucket=1_30` (etc,
    matching accounting.selectors.AGING_BUCKETS) to narrow `results` to just
    that bucket — the summary itself does NOT narrow, so the cards stay a
    stable reference point while the table filters underneath them.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = ARAgingRowSerializer

    def list(self, request, *args, **kwargs):
        # Paginates the QUERYSET, so only the page's rows cross the network.
        # Previously every outstanding invoice was materialized and sorted in
        # Python just to slice 25 of them out. The summary is a separate
        # GROUP BY over the unfiltered set, so it still describes the whole
        # outstanding book even when `bucket` narrows the table below it.
        bucket = request.query_params.get("bucket")
        summary = get_ar_aging_summary()

        page = self.paginate_queryset(get_ar_aging_queryset(bucket=bucket))
        rows = [ar_aging_row(inv) for inv in page]
        serializer = self.get_serializer(rows, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["summary"] = summary
        return response


class ARAgingPrintView(APIView):
    """
    GET /accounting/ar-aging/print/?bucket=1_30 — same shape as
    reports.views's BaseReportPrintView subclasses (same PDF template/
    renderer), prints exactly the currently-applied bucket filter, never
    "everything" if a bucket is selected on screen.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        bucket = request.query_params.get("bucket")
        # ONE fetch, not two. The summary is deliberately over ALL rows (the
        # PDF's "Total Outstanding (All)" stat) while `rows` is the filtered
        # set, but that never needed a second full scan + re-bucketing:
        # get_ar_aging_rows applies `bucket` as a plain Python post-filter on
        # the derived bucket key, so filtering here is exactly equivalent.
        all_rows = get_ar_aging_rows()
        summary = get_ar_aging_summary(all_rows)
        rows = [r for r in all_rows if r["bucket"] == bucket] if bucket else all_rows
        # `summary` is computed BEFORE capping and from the unfiltered set, so
        # the printed totals still describe every outstanding invoice even
        # when the row list below them is truncated.
        rows, truncation_notice = _cap_print_rows(rows, noun="invoices")

        columns = [
            {"key": "bill_number", "label": "Invoice #"},
            {"key": "customer_name", "label": "Customer"},
            {"key": "customer_code", "label": "Code"},
            {"key": "due_date", "label": "Due Date"},
            {"key": "days_overdue", "label": "Days Overdue"},
            {"key": "bucket", "label": "Bucket"},
            {"key": "outstanding", "label": "Outstanding (PKR)"},
        ]
        stats = [
            {"label": "Invoices Shown", "value": len(rows)},
            {"label": "Total Outstanding (All)", "value": _fmt(summary["grand_total"])},
            {"label": "Current", "value": _fmt(summary["buckets"]["current"]["total"])},
            {"label": "1-30 Days", "value": _fmt(summary["buckets"]["1_30"]["total"])},
            {"label": "31-60 Days", "value": _fmt(summary["buckets"]["31_60"]["total"])},
            {"label": "61-90 Days", "value": _fmt(summary["buckets"]["61_90"]["total"])},
            {"label": "Over 90 Days", "value": _fmt(summary["buckets"]["over_90"]["total"])},
        ]

        pdf_bytes, filename = generate_report_pdf_bytes(
            title="A/R Aging Report",
            filter_description=(f"Bucket: {bucket}" if bucket else "All buckets") + truncation_notice,
            columns=columns,
            rows=ARAgingRowSerializer(rows, many=True).data,
            stats=stats,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# A/P Aging
# ---------------------------------------------------------------------------

class APAgingListView(generics.ListAPIView):
    """GET /accounting/ap-aging/?bucket=1_30 — same shape as ARAgingListView."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = APAgingRowSerializer

    def list(self, request, *args, **kwargs):
        # Same shape as ARAgingListView.list — see there for why.
        bucket = request.query_params.get("bucket")
        summary = get_ap_aging_summary()

        page = self.paginate_queryset(get_ap_aging_queryset(bucket=bucket))
        rows = [ap_aging_row(o) for o in page]
        serializer = self.get_serializer(rows, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["summary"] = summary
        return response


class APAgingPrintView(APIView):
    """GET /accounting/ap-aging/print/?bucket=1_30 — same shape as ARAgingPrintView."""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        bucket = request.query_params.get("bucket")
        # ONE fetch, not two — see ARAgingPrintView.get for why this is
        # equivalent to the previous double-scan.
        all_rows = get_ap_aging_rows()
        summary = get_ap_aging_summary(all_rows)
        rows = [r for r in all_rows if r["bucket"] == bucket] if bucket else all_rows
        rows, truncation_notice = _cap_print_rows(rows, noun="orders")

        columns = [
            {"key": "order_number", "label": "Order #"},
            {"key": "supplier_name", "label": "Supplier"},
            {"key": "supplier_code", "label": "Code"},
            {"key": "confirmed_date", "label": "Confirmed On"},
            {"key": "days_overdue", "label": "Days Since Confirmed"},
            {"key": "bucket", "label": "Bucket"},
            {"key": "outstanding", "label": "Outstanding (PKR)"},
        ]
        stats = [
            {"label": "Orders Shown", "value": len(rows)},
            {"label": "Total Outstanding (All)", "value": _fmt(summary["grand_total"])},
            {"label": "Current", "value": _fmt(summary["buckets"]["current"]["total"])},
            {"label": "1-30 Days", "value": _fmt(summary["buckets"]["1_30"]["total"])},
            {"label": "31-60 Days", "value": _fmt(summary["buckets"]["31_60"]["total"])},
            {"label": "61-90 Days", "value": _fmt(summary["buckets"]["61_90"]["total"])},
            {"label": "Over 90 Days", "value": _fmt(summary["buckets"]["over_90"]["total"])},
        ]

        pdf_bytes, filename = generate_report_pdf_bytes(
            title="A/P Aging Report",
            filter_description=(f"Bucket: {bucket}" if bucket else "All buckets") + truncation_notice,
            columns=columns,
            rows=APAgingRowSerializer(rows, many=True).data,
            stats=stats,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Cash Flow Statement
# ---------------------------------------------------------------------------

class CashFlowStatementView(APIView):
    """
    GET /accounting/cash-flow-statement/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    Defaults to current-month-to-date when either param is omitted.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        today = timezone.localdate()
        date_from = request.query_params.get("date_from") or today.replace(day=1).isoformat()
        date_to = request.query_params.get("date_to") or today.isoformat()

        data = get_cash_flow_statement(date_from=date_from, date_to=date_to)
        return Response(CashFlowStatementSerializer(data).data)


class CashFlowStatementPrintView(APIView):
    """
    GET /accounting/cash-flow-statement/print/?date_from=...&date_to=...
    Prints exactly the range the caller passes — same params as
    CashFlowStatementView, no separate filter logic to drift out of sync.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        today = timezone.localdate()
        date_from = request.query_params.get("date_from") or today.replace(day=1).isoformat()
        date_to = request.query_params.get("date_to") or today.isoformat()

        data = get_cash_flow_statement(date_from=date_from, date_to=date_to)

        def _activity_lines(activity):
            lines = [{"label": l["label"], "amount": _fmt(l["amount"])} for l in activity["lines"]]
            lines.append({"label": "Net", "amount": _fmt(activity["net"]), "bold": True})
            return lines

        sections = [
            {
                "heading": "Operating Activities",
                "subtitle": "Cash from everyday running of the business.",
                "lines": _activity_lines(data["operating"]),
            },
            {
                "heading": "Investing Activities",
                "subtitle": "Cash from buying or selling long-term assets.",
                "lines": _activity_lines(data["investing"]),
            },
            {
                "heading": "Financing Activities",
                "subtitle": "Cash from owners/investors putting money in or taking it out.",
                "lines": _activity_lines(data["financing"]),
            },
            {
                "heading": "Summary",
                "lines": [
                    *([{"label": "Cash You Started With", "amount": _fmt(data["opening_cash"])}]
                      if data["opening_cash"] is not None else []),
                    *([{"label": "Cash You Have Now", "amount": _fmt(data["closing_cash"])}]
                      if data["closing_cash"] is not None else []),
                    {"label": "Net Change in Cash", "amount": _fmt(data["net_change_in_cash"]), "bold": True},
                ],
            },
        ]

        pdf_bytes, filename = generate_statement_pdf_bytes(
            title="Cash Flow Statement",
            filter_description=f"{date_from} to {date_to}",
            sections=sections,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Income Statement
# ---------------------------------------------------------------------------

class IncomeStatementView(APIView):
    """GET /accounting/income-statement/?period=YYYY-MM — defaults to the current month (provisional)."""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        from profits.models import MonthlyProfit

        period = request.query_params.get("period")
        try:
            data = get_income_statement(period=period)
        except MonthlyProfit.DoesNotExist:
            return Response(
                {"detail": f"No finalized Income Statement exists for period '{period}'."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(IncomeStatementSerializer(data).data)


class IncomeStatementPrintView(APIView):
    """GET /accounting/income-statement/print/?period=YYYY-MM"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        from profits.models import MonthlyProfit

        period = request.query_params.get("period")
        try:
            data = get_income_statement(period=period)
        except MonthlyProfit.DoesNotExist:
            return Response(
                {"detail": f"No finalized Income Statement exists for period '{period}'."},
                status=status.HTTP_404_NOT_FOUND,
            )

        sections = self._build_sections(data)

        period_label = data["period"] + (" (provisional — month still in progress)" if data["is_provisional"] else "")
        pdf_bytes, filename = generate_statement_pdf_bytes(
            title="Income Statement",
            filter_description=f"Period: {period_label}",
            sections=sections,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response

    def _build_sections(self, data):
        """Extracted from get() purely so the printed content can be asserted
        in tests without rendering a PDF — in particular that the Operating
        Expenses lines add up to their own subtotal."""
        total_opex = (
            Decimal(data["expenses_paid"]) + Decimal(data["recurring_expenses_paid"])
            + Decimal(data["gst_paid"]) + Decimal(data["wht_paid"]) + Decimal(data["depreciation"])
        )

        return [
            {
                "heading": "Revenue",
                "subtitle": "Total sales made this period.",
                "lines": [
                    {"label": "Sales Revenue", "amount": _fmt(data["net_revenue"])},
                    {"label": "Cost of Goods Sold", "amount": _fmt(data["net_cogs"])},
                    {"label": "Gross Profit", "amount": _fmt(data["net_gross_profit"]), "bold": True},
                ],
            },
            {
                "heading": "Operating Expenses",
                "subtitle": "Day-to-day costs of running the business. One-off expenses are listed "
                            "by category; recurring expenses are shown as a single total on their "
                            "own line.",
                "lines": [
                    *[{"label": b["category"] or "Uncategorized", "amount": _fmt(b["amount"])}
                      for b in data["expense_breakdown"]],
                    {"label": "Recurring Expenses", "amount": _fmt(data["recurring_expenses_paid"])},
                    {"label": "GST Paid", "amount": _fmt(data["gst_paid"])},
                    {"label": "WHT Paid", "amount": _fmt(data["wht_paid"])},
                    {"label": "Depreciation", "amount": _fmt(data["depreciation"])},
                    {"label": "Total Operating Expenses", "amount": _fmt(total_opex), "bold": True},
                ],
            },
            {
                "heading": "Other Items",
                "subtitle": "Cash/inventory found or lost, and gains or losses from selling equipment.",
                "lines": [
                    {"label": "Cash Lost", "amount": _fmt(data["lost_cash"])},
                    {"label": "Cash Found", "amount": _fmt(data["found_cash"])},
                    {"label": "Inventory Lost", "amount": _fmt(data["lost_inventory"])},
                    {"label": "Inventory Found", "amount": _fmt(data["found_inventory"])},
                    {"label": "Gain/(Loss) on Asset Disposal", "amount": _fmt(data["disposal_gain_loss"])},
                ],
            },
            {
                "heading": "Net Income",
                "lines": [{"label": "Net Income", "amount": _fmt(data["net_profit"]), "bold": True}],
            },
        ]


# ---------------------------------------------------------------------------
# Balance Sheet
# ---------------------------------------------------------------------------

class BalanceSheetView(APIView):
    """GET /accounting/balance-sheet/?period=YYYY-MM — omit `period` for the live "as of today" view."""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        from .models import BalanceSheetSnapshot

        period = request.query_params.get("period")
        if period:
            try:
                data = get_balance_sheet_for_period(period)
            except BalanceSheetSnapshot.DoesNotExist:
                return Response(
                    {"detail": f"No Balance Sheet snapshot exists for period '{period}'. "
                               f"Only the most recently finished month gets snapshotted automatically."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            data = get_balance_sheet_live()
        return Response(BalanceSheetSerializer(data).data)


class BalanceSheetPrintView(APIView):
    """GET /accounting/balance-sheet/print/?period=YYYY-MM — omit `period` for "as of today"."""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        from .models import BalanceSheetSnapshot

        period = request.query_params.get("period")
        if period:
            try:
                data = get_balance_sheet_for_period(period)
            except BalanceSheetSnapshot.DoesNotExist:
                return Response(
                    {"detail": f"No Balance Sheet snapshot exists for period '{period}'. "
                               f"Only the most recently finished month gets snapshotted automatically."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            filter_description = f"As of {period} (finished month)"
            # A late snapshot is silently wrong (see selectors._snapshot_freshness),
            # so the printed copy has to carry the same caveat the page does —
            # a PDF outlives the screen it was printed from.
            freshness = data["freshness"]
            if freshness["is_stale"]:
                filter_description += (
                    f" — WARNING: frozen {freshness['lag_days']} days after the month ended "
                    f"({freshness['snapshot_taken_on'].isoformat()}), so it may include activity "
                    f"from the following month. Treat these figures as approximate."
                )
        else:
            data = get_balance_sheet_live()
            filter_description = f"As of today ({timezone.localdate().isoformat()})"

        sections = [
            {
                "heading": "Assets",
                "subtitle": "Everything the business owns.",
                "lines": [
                    {"label": "Cash in Hand", "amount": _fmt(data["assets"]["cash_in_hand"])},
                    {"label": "Money Customers Owe You", "amount": _fmt(data["assets"]["accounts_receivable"])},
                    {"label": "Inventory Value", "amount": _fmt(data["assets"]["inventory_value"])},
                    {"label": "Equipment & Fixed Assets", "amount": _fmt(data["assets"]["fixed_assets_nbv"])},
                    {"label": "Total Assets", "amount": _fmt(data["assets"]["total"]), "bold": True},
                ],
            },
            {
                "heading": "Liabilities",
                "subtitle": "Everything the business owes.",
                "lines": [
                    {"label": "Money You Owe Suppliers", "amount": _fmt(data["liabilities"]["accounts_payable"])},
                    {"label": "GST Owed to FBR", "amount": _fmt(data["liabilities"]["gst_payable"])},
                    {"label": "WHT Owed to FBR", "amount": _fmt(data["liabilities"]["wht_payable"])},
                    {"label": "Total Liabilities", "amount": _fmt(data["liabilities"]["total"]), "bold": True},
                ],
            },
            {
                "heading": "Equity",
                "subtitle": "The owner's stake in the business.",
                "lines": [
                    {"label": "Owner's Capital", "amount": _fmt(data["equity"]["owner_capital"])},
                    {"label": "Investors' Capital", "amount": _fmt(data["equity"]["investor_capital"])},
                    {"label": "Opening Balance (Pre-Existing Debts/Stock)",
                     "amount": _fmt(data["equity"]["opening_balance_equity"])},
                    {"label": "Equipment You Already Owned",
                     "amount": _fmt(data["equity"]["pre_owned_asset_equity"])},
                    {"label": "Increase in Equipment Value (Revaluation)",
                     "amount": _fmt(data["equity"]["asset_revaluation_surplus"])},
                    {"label": "Retained Earnings (Undistributed Profit)", "amount": _fmt(data["equity"]["retained_earnings"])},
                    {"label": "Total Equity", "amount": _fmt(data["equity"]["total"]), "bold": True},
                ],
            },
        ]

        balance_check = {
            "is_balanced": data["is_balanced"],
            "message": (
                "Balanced — Assets exactly equal Liabilities + Equity."
                if data["is_balanced"]
                else f"Off by Rs. {_fmt(abs(data['balance_check']))} — this needs investigating."
            ),
        }

        pdf_bytes, filename = generate_statement_pdf_bytes(
            title="Balance Sheet",
            filter_description=filter_description,
            sections=sections,
            balance_check=balance_check,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Fixed Asset Register
# ---------------------------------------------------------------------------

class FixedAssetRegisterListView(generics.ListAPIView):
    """
    GET /accounting/fixed-asset-register/?include_disposed=true — paginated.
    Excludes disposed assets by default (mirrors the Assets page convention).
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = FixedAssetRegisterRowSerializer

    def get_queryset(self):
        include_disposed = self.request.query_params.get("include_disposed") == "true"
        return get_fixed_asset_register_rows(include_disposed=include_disposed)

    def list(self, request, *args, **kwargs):
        rows = self.get_queryset()
        summary = get_fixed_asset_register_summary(rows)
        page = self.paginate_queryset(rows)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["summary"] = summary
        return response


class FixedAssetRegisterPrintView(APIView):
    """GET /accounting/fixed-asset-register/print/?include_disposed=true"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        include_disposed = request.query_params.get("include_disposed") == "true"
        rows = get_fixed_asset_register_rows(include_disposed=include_disposed)
        summary = get_fixed_asset_register_summary(rows)

        columns = [
            {"key": "name", "label": "Asset"},
            {"key": "category", "label": "Category"},
            {"key": "acquisition_date", "label": "Acquired"},
            {"key": "cost", "label": "Cost (PKR)"},
            {"key": "accumulated_depreciation", "label": "Accum. Depreciation (PKR)"},
            {"key": "net_book_value", "label": "Net Book Value (PKR)"},
            {"key": "is_disposed", "label": "Disposed"},
        ]
        stats = [
            {"label": "Asset Count", "value": summary["asset_count"]},
            {"label": "Total Cost", "value": _fmt(summary["total_cost"])},
            {"label": "Accum. Depreciation", "value": _fmt(summary["total_accumulated_depreciation"])},
            {"label": "Net Book Value", "value": _fmt(summary["total_net_book_value"])},
        ]

        pdf_bytes, filename = generate_report_pdf_bytes(
            title="Fixed Asset Register",
            filter_description="Including disposed assets" if include_disposed else "Active assets only",
            columns=columns,
            rows=FixedAssetRegisterRowSerializer(rows, many=True).data,
            stats=stats,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response
