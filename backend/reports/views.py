from django.http import HttpResponse
from rest_framework import generics
from rest_framework.views import APIView

from .pdf_service import generate_report_pdf_bytes
from .permissions import IsAdminOrSuperuser
from .selectors import (
    get_asset_depreciation_report_queryset,
    get_asset_depreciation_report_stats,
    get_asset_depreciation_report_stats_all_time,
    get_cash_collected_report_queryset,
    get_cash_collected_report_stats,
    get_cash_collected_report_stats_all_time,
    get_customer_returns_report_queryset,
    get_customer_returns_report_stats,
    get_customer_returns_report_stats_all_time,
    get_expenses_report_queryset,
    get_expenses_report_stats,
    get_expenses_report_stats_all_time,
    get_input_tax_report_queryset,
    get_input_tax_report_stats,
    get_input_tax_report_stats_all_time,
    get_inventory_valuation_report_data,
    get_inventory_valuation_report_stats,
    get_invoices_report_queryset,
    get_invoices_report_stats,
    get_invoices_report_stats_all_time,
    get_lost_inventory_report_queryset,
    get_lost_inventory_report_stats,
    get_lost_inventory_report_stats_all_time,
    get_net_profit_report_queryset,
    get_net_profit_report_stats,
    get_net_profit_report_stats_all_time,
    get_output_tax_report_queryset,
    get_output_tax_report_stats,
    get_output_tax_report_stats_all_time,
    get_profit_margin_report_queryset,
    get_profit_margin_report_stats,
    get_profit_margin_report_stats_all_time,
    get_purchase_returns_report_queryset,
    get_purchase_returns_report_stats,
    get_purchase_returns_report_stats_all_time,
    get_recurring_expenses_report_queryset,
    get_recurring_expenses_report_stats,
    get_recurring_expenses_report_stats_all_time,
    get_stock_movement_report_rows,
    get_stock_movement_report_stats,
    get_stock_movement_report_stats_all_time,
)
from .serializers import (
    AssetDepreciationReportItemSerializer,
    CustomerReturnReportItemSerializer,
    ExpenseReportItemSerializer,
    InputTaxReportItemSerializer,
    InventoryValuationReportItemSerializer,
    InvoiceReportItemSerializer,
    LostInventoryReportItemSerializer,
    NetProfitReportItemSerializer,
    OutputTaxReportItemSerializer,
    PaymentReportItemSerializer,
    ProfitMarginReportItemSerializer,
    PurchaseReturnReportItemSerializer,
    RecurringExpenseReportItemSerializer,
    ReportDateFilterSerializer,
    StockMovementReportItemSerializer,
)


def _has_date_filter(request) -> bool:
    """
    True if the caller supplied any date/date_from/date_to query param.
    When false, views read stats from the pre-synced CashFlow totals instead
    of aggregating the full table — see reports/selectors.py's
    get_<name>_report_stats_all_time() functions.
    """
    p = request.query_params
    return bool(p.get("date") or p.get("date_from") or p.get("date_to"))


class InvoicesReportView(generics.ListAPIView):
    """
    GET /reports/invoices/
    Non-draft invoices, filtered by confirmed date.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_invoices": int, "total_invoices_cash": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = InvoiceReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_invoices_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        # No filter → read the pre-synced CashFlow total (instant at any scale).
        # Filtered → stats computed over the FULL filtered queryset, before
        # pagination slices it down to one page.
        if _has_date_filter(request):
            stats = get_invoices_report_stats(queryset)
        else:
            stats = get_invoices_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class CashCollectedReportView(generics.ListAPIView):
    """
    GET /reports/cash-collected/
    All payment collections (any method), filtered by payment date.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_payments": int, "total_cash_collected": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = PaymentReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_cash_collected_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            stats = get_cash_collected_report_stats(queryset)
        else:
            stats = get_cash_collected_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class ExpensesReportView(generics.ListAPIView):
    """
    GET /reports/expenses/
    All non-deleted expenses, filtered by expense date.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_expenses": int, "total_expenses_cash": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = ExpenseReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_expenses_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            stats = get_expenses_report_stats(queryset)
        else:
            stats = get_expenses_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class LostInventoryReportView(generics.ListAPIView):
    """
    GET /reports/lost-inventory/
    Every product lost in a batch, filtered by the batch's record date.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_lost_items": int, "total_lost_cash": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = LostInventoryReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_lost_inventory_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            stats = get_lost_inventory_report_stats(queryset)
        else:
            stats = get_lost_inventory_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class PurchaseReturnsReportView(generics.ListAPIView):
    """
    GET /reports/purchase-returns/
    Accepted returns to suppliers, filtered by accepted date.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_returns": int, "total_return_value": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = PurchaseReturnReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_purchase_returns_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            stats = get_purchase_returns_report_stats(queryset)
        else:
            stats = get_purchase_returns_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class CustomerReturnsReportView(generics.ListAPIView):
    """
    GET /reports/customer-returns/
    Accepted returns from customers, filtered by accepted date.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_returns": int, "total_return_value": decimal, "total_return_cogs": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = CustomerReturnReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_customer_returns_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            stats = get_customer_returns_report_stats(queryset)
        else:
            stats = get_customer_returns_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class ProfitMarginReportView(generics.ListAPIView):
    """
    GET /reports/profit-margin/
    Non-draft invoices with revenue/COGS/profit, filtered by confirmed date.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_invoices": int, "total_revenue": decimal,
                    "total_cogs": decimal, "total_gross_profit": decimal,
                    "net_revenue": decimal, "net_cogs": decimal, "net_gross_profit": decimal},
         "results": [...]}

    total_revenue/total_cogs/total_gross_profit are GROSS — the historical
    "as sold" figures, never reduced by later returns. net_revenue/net_cogs/
    net_gross_profit subtract returns accepted within the same date window.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = ProfitMarginReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_profit_margin_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            filters = ReportDateFilterSerializer(data=request.query_params)
            filters.is_valid(raise_exception=True)
            stats = get_profit_margin_report_stats(queryset, **filters.validated_data)
        else:
            stats = get_profit_margin_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class InventoryValuationReportView(generics.ListAPIView):
    """
    GET /reports/inventory-valuation/
    Live snapshot of current stock valued at FIFO cost. No date filtering —
    this answers "what is my stock worth right now", not a period report.

    Query params:
        search : product name/code (partial match, optional)

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_products": int, "total_quantity_on_hand": int,
                    "total_inventory_value": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = InventoryValuationReportItemSerializer

    def get_queryset(self):
        return get_inventory_valuation_report_data(search=self.request.query_params.get("search"))

    def list(self, request, *args, **kwargs):
        rows = self.get_queryset()
        stats = get_inventory_valuation_report_stats(rows)

        page = self.paginate_queryset(rows)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class InputTaxReportView(generics.ListAPIView):
    """
    GET /reports/sales-tax/input/
    Confirmed purchase orders — the "Input Tax" side of the Sales Tax report
    (GST paid to suppliers, WHT withheld from suppliers). Filtered by
    confirmed date.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_orders": int, "total_input_tax_paid": decimal,
                    "total_wht_withheld": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = InputTaxReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_input_tax_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            stats = get_input_tax_report_stats(queryset)
        else:
            stats = get_input_tax_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class OutputTaxReportView(generics.ListAPIView):
    """
    GET /reports/sales-tax/output/
    Confirmed, non-draft invoices — the "Output Tax" side of the Sales Tax
    report (GST charged to customers, WHT withheld by customers). Filtered
    by confirmed date.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_invoices": int, "total_output_tax_collected": decimal,
                    "total_wht_withheld": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = OutputTaxReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_output_tax_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            stats = get_output_tax_report_stats(queryset)
        else:
            stats = get_output_tax_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class RecurringExpensesReportView(generics.ListAPIView):
    """
    GET /reports/recurring-expenses/
    Every recurring expense assignment — the underlying transactions behind
    the Recurring Expenses app's Monthly Breakdown page. Filtered by the
    date each due bill was posted.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_assignments": int, "total_assigned_amount": decimal,
                    "total_paid_amount": decimal, "total_pending_amount": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = RecurringExpenseReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_recurring_expenses_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            stats = get_recurring_expenses_report_stats(queryset)
        else:
            stats = get_recurring_expenses_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class StockMovementReportView(generics.ListAPIView):
    """
    GET /reports/stock-movement/
    One row per product: quantity purchased, purchase-returned, sold, and
    sale-returned. Header stats are the same four totals summed across
    every product.

    Query params:
        date      : YYYY-MM-DD — exact day
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end
        search    : matches product name or code. No search -> header
                    stats cover every product. With search -> header stats
                    are scoped to just the matching products, same set the
                    row list shows.

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_purchased": int, "total_purchase_returned": int,
                    "total_sold": int, "total_sale_returned": int},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = StockMovementReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        search = self.request.query_params.get("search")
        return get_stock_movement_report_rows(**filters.validated_data, search=search)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        search = request.query_params.get("search")
        if _has_date_filter(request) or (search and search.strip()):
            # Sums the SAME rows list above — no second aggregation query.
            # Used to call get_stock_movement_report_stats(**filters, search)
            # here, which independently re-ran the full 6-table aggregation
            # a second time every request.
            stats = get_stock_movement_report_stats(queryset)
        else:
            stats = get_stock_movement_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class NetProfitReportView(generics.ListAPIView):
    """
    GET /reports/net-profit/
    One row per FINALIZED month, with the full deduction breakdown down to
    net_profit — the real counterpart to Profit Margin Report. Filtered by
    period (translated from date/date_from/date_to — YYYY-MM-DD -> YYYY-MM,
    since MonthlyProfit is keyed by period, not a literal date field). The
    current, still-open month never appears here.

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day (matched to that day's month)
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_months": int, "total_gross_profit": decimal,
                    "total_net_gross_profit": decimal, "total_net_profit": decimal,
                    "total_investor_share": decimal, "total_owner_share": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = NetProfitReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_net_profit_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            stats = get_net_profit_report_stats(queryset)
        else:
            stats = get_net_profit_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


class AssetDepreciationReportView(generics.ListAPIView):
    """
    GET /reports/asset-depreciation/
    One row per depreciation posting, across every asset — the number that
    silently feeds into Monthly Profit's depreciation figure, now with its
    own visibility. Filtered by period (translated from date/date_from/
    date_to — the period the depreciation applies to, not the day it was
    computed).

    Query params (mutually exclusive with each other where noted):
        date      : YYYY-MM-DD — exact day (matched to that day's month)
        date_from : YYYY-MM-DD — range start
        date_to   : YYYY-MM-DD — range end

    Response (paginated):
        {"count": int, "total_pages": int, "current_page": int, "page_size": int,
         "stats": {"total_entries": int, "total_depreciation": decimal},
         "results": [...]}
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = AssetDepreciationReportItemSerializer

    def get_queryset(self):
        filters = ReportDateFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        return get_asset_depreciation_report_queryset(**filters.validated_data)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if _has_date_filter(request):
            stats = get_asset_depreciation_report_stats(queryset)
        else:
            stats = get_asset_depreciation_report_stats_all_time()

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        response = self.get_paginated_response(serializer.data)
        response.data["stats"] = stats
        return response


# ---------------------------------------------------------------------------
# Print (PDF) — one generic base view, every report just supplies its own
# queryset/stats functions, serializer, title, and column list. Honors the
# SAME date filter as the on-screen report; no filter means every matching
# row prints (no pagination — this is the one place a report reads its full
# result set at once, by design).
# ---------------------------------------------------------------------------

def _describe_filters(query_params) -> str:
    date      = query_params.get("date")
    date_from = query_params.get("date_from")
    date_to   = query_params.get("date_to")
    if date:
        return f"Exact date: {date}"
    if date_from and date_to:
        return f"From {date_from} to {date_to}"
    if date_from:
        return f"From {date_from} onward"
    if date_to:
        return f"Up to {date_to}"
    return "All records — no filter applied"


def _humanize(key: str) -> str:
    return key.replace("_", " ").title()


class BaseReportPrintView(APIView):
    """
    Not registered directly — subclasses set title/columns/queryset_fn/
    stats_fn/stats_all_time_fn/serializer_class and inherit this get().
    stats_needs_filters=True is only for Profit Margin, whose stats function
    also needs the raw date filters (see get_profit_margin_report_stats).
    """
    permission_classes  = [IsAdminOrSuperuser]
    title               = None
    columns             = []
    queryset_fn         = None
    stats_fn            = None
    stats_all_time_fn   = None
    serializer_class    = None
    stats_needs_filters = False

    def get(self, request):
        filters_serializer = ReportDateFilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)
        filters = filters_serializer.validated_data

        queryset = self.queryset_fn(**filters)

        if request.query_params.get("date") or request.query_params.get("date_from") or request.query_params.get("date_to"):
            stats = self.stats_fn(queryset, **filters) if self.stats_needs_filters else self.stats_fn(queryset)
        else:
            stats = self.stats_all_time_fn()

        rows = self.serializer_class(queryset, many=True).data

        pdf_bytes, filename = generate_report_pdf_bytes(
            title=self.title,
            filter_description=_describe_filters(request.query_params),
            columns=self.columns,
            rows=rows,
            stats=[{"label": _humanize(k), "value": v} for k, v in stats.items()],
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class InvoicesReportPrintView(BaseReportPrintView):
    title             = "Invoices Report"
    columns           = [
        {"key": "bill_number", "label": "Bill #"}, {"key": "customer_name", "label": "Customer"},
        {"key": "grand_total", "label": "Grand Total"}, {"key": "payment_status", "label": "Status"},
        {"key": "confirmed_at", "label": "Date"}, {"key": "payment_due_date", "label": "Due Date"},
    ]
    queryset_fn       = staticmethod(get_invoices_report_queryset)
    stats_fn          = staticmethod(get_invoices_report_stats)
    stats_all_time_fn = staticmethod(get_invoices_report_stats_all_time)
    serializer_class  = InvoiceReportItemSerializer


class CashCollectedReportPrintView(BaseReportPrintView):
    title             = "Cash Collected Report"
    columns           = [
        {"key": "reference_number", "label": "Reference #"}, {"key": "invoice_bill_number", "label": "Bill #"},
        {"key": "customer_name", "label": "Customer"}, {"key": "amount", "label": "Amount"},
        {"key": "method_display", "label": "Method"}, {"key": "payment_date", "label": "Date"},
    ]
    queryset_fn       = staticmethod(get_cash_collected_report_queryset)
    stats_fn          = staticmethod(get_cash_collected_report_stats)
    stats_all_time_fn = staticmethod(get_cash_collected_report_stats_all_time)
    serializer_class  = PaymentReportItemSerializer


class ExpensesReportPrintView(BaseReportPrintView):
    title             = "Expenses Report"
    columns           = [
        {"key": "name", "label": "Expense"}, {"key": "category_name", "label": "Category"},
        {"key": "amount", "label": "Amount"}, {"key": "expense_date", "label": "Date"},
    ]
    queryset_fn       = staticmethod(get_expenses_report_queryset)
    stats_fn          = staticmethod(get_expenses_report_stats)
    stats_all_time_fn = staticmethod(get_expenses_report_stats_all_time)
    serializer_class  = ExpenseReportItemSerializer


class LostInventoryReportPrintView(BaseReportPrintView):
    title             = "Lost Inventory Report"
    columns           = [
        {"key": "reference_number", "label": "Reference #"}, {"key": "product_name", "label": "Product"},
        {"key": "product_code", "label": "Code"}, {"key": "quantity", "label": "Qty"},
        {"key": "found_quantity", "label": "Found Qty"}, {"key": "reason", "label": "Reason"},
        {"key": "unit_cost", "label": "Unit Cost"}, {"key": "total_cost", "label": "Total Cost"},
        {"key": "recovered_amount", "label": "Recovered"}, {"key": "net_amount", "label": "Net Loss"},
        {"key": "created_at", "label": "Date"},
    ]
    queryset_fn       = staticmethod(get_lost_inventory_report_queryset)
    stats_fn          = staticmethod(get_lost_inventory_report_stats)
    stats_all_time_fn = staticmethod(get_lost_inventory_report_stats_all_time)
    serializer_class  = LostInventoryReportItemSerializer


class PurchaseReturnsReportPrintView(BaseReportPrintView):
    title             = "Purchase Returns Report"
    columns           = [
        {"key": "reference_number", "label": "Reference #"}, {"key": "order_number", "label": "Order #"},
        {"key": "supplier_name", "label": "Supplier"}, {"key": "total_return_gross", "label": "Gross"},
        {"key": "total_return_gst", "label": "GST"}, {"key": "total_return_wht", "label": "WHT"},
        {"key": "total_return_amount", "label": "Total Return"}, {"key": "accepted_at", "label": "Accepted On"},
    ]
    queryset_fn       = staticmethod(get_purchase_returns_report_queryset)
    stats_fn          = staticmethod(get_purchase_returns_report_stats)
    stats_all_time_fn = staticmethod(get_purchase_returns_report_stats_all_time)
    serializer_class  = PurchaseReturnReportItemSerializer


class CustomerReturnsReportPrintView(BaseReportPrintView):
    title             = "Customer Returns Report"
    columns           = [
        {"key": "reference_number", "label": "Reference #"}, {"key": "bill_number", "label": "Bill #"},
        {"key": "customer_name", "label": "Customer"}, {"key": "total_return_amount", "label": "Total Return"},
        {"key": "total_return_cogs", "label": "COGS"}, {"key": "accepted_at", "label": "Accepted On"},
    ]
    queryset_fn       = staticmethod(get_customer_returns_report_queryset)
    stats_fn          = staticmethod(get_customer_returns_report_stats)
    stats_all_time_fn = staticmethod(get_customer_returns_report_stats_all_time)
    serializer_class  = CustomerReturnReportItemSerializer


class ProfitMarginReportPrintView(BaseReportPrintView):
    title               = "Profit / Margin Report"
    columns             = [
        {"key": "bill_number", "label": "Bill #"}, {"key": "customer_name", "label": "Customer"},
        {"key": "grand_total", "label": "Revenue"}, {"key": "total_cogs", "label": "COGS"},
        {"key": "gross_profit", "label": "Gross Profit"}, {"key": "margin_percent", "label": "Margin %"},
        {"key": "confirmed_at", "label": "Date"},
    ]
    queryset_fn         = staticmethod(get_profit_margin_report_queryset)
    stats_fn            = staticmethod(get_profit_margin_report_stats)
    stats_all_time_fn   = staticmethod(get_profit_margin_report_stats_all_time)
    serializer_class    = ProfitMarginReportItemSerializer
    stats_needs_filters = True


class InputTaxReportPrintView(BaseReportPrintView):
    title             = "Sales Tax Report — Input Tax"
    columns           = [
        {"key": "order_number", "label": "Order #"}, {"key": "supplier_name", "label": "Supplier"},
        {"key": "supplier_code", "label": "Code"}, {"key": "gst_total", "label": "GST Paid"},
        {"key": "wht_total", "label": "WHT Withheld"}, {"key": "net_payable", "label": "Net Payable"},
        {"key": "confirmed_at", "label": "Date"},
    ]
    queryset_fn       = staticmethod(get_input_tax_report_queryset)
    stats_fn          = staticmethod(get_input_tax_report_stats)
    stats_all_time_fn = staticmethod(get_input_tax_report_stats_all_time)
    serializer_class  = InputTaxReportItemSerializer


class OutputTaxReportPrintView(BaseReportPrintView):
    title             = "Sales Tax Report — Output Tax"
    columns           = [
        {"key": "bill_number", "label": "Bill #"}, {"key": "customer_name", "label": "Customer"},
        {"key": "customer_code", "label": "Code"}, {"key": "gst_total", "label": "GST Collected"},
        {"key": "wht_total", "label": "WHT Withheld"}, {"key": "grand_total", "label": "Grand Total"},
        {"key": "confirmed_at", "label": "Date"},
    ]
    queryset_fn       = staticmethod(get_output_tax_report_queryset)
    stats_fn          = staticmethod(get_output_tax_report_stats)
    stats_all_time_fn = staticmethod(get_output_tax_report_stats_all_time)
    serializer_class  = OutputTaxReportItemSerializer


class RecurringExpensesReportPrintView(BaseReportPrintView):
    title             = "Recurring Expenses Report"
    columns           = [
        {"key": "name_snapshot", "label": "Expense"}, {"key": "category_name_snapshot", "label": "Category"},
        {"key": "period", "label": "For Month"}, {"key": "amount", "label": "Amount"},
        {"key": "amount_paid", "label": "Paid"}, {"key": "payment_status", "label": "Status"},
        {"key": "assigned_at", "label": "Assigned On"},
    ]
    queryset_fn       = staticmethod(get_recurring_expenses_report_queryset)
    stats_fn          = staticmethod(get_recurring_expenses_report_stats)
    stats_all_time_fn = staticmethod(get_recurring_expenses_report_stats_all_time)
    serializer_class  = RecurringExpenseReportItemSerializer


class NetProfitReportPrintView(BaseReportPrintView):
    title             = "Net Profit Report"
    columns           = [
        {"key": "period", "label": "Month"}, {"key": "gross_profit", "label": "Gross Profit"},
        {"key": "net_gross_profit", "label": "Net Gross Profit"}, {"key": "expenses_paid", "label": "Expenses"},
        {"key": "recurring_expenses_paid", "label": "Recurring Exp."}, {"key": "gst_paid", "label": "GST Paid"},
        {"key": "wht_paid", "label": "WHT Paid"},
        {"key": "lost_cash", "label": "Lost Cash"}, {"key": "found_cash", "label": "Found Cash"},
        {"key": "lost_inventory", "label": "Lost Inventory"}, {"key": "found_inventory", "label": "Found Inventory"},
        {"key": "depreciation", "label": "Depreciation"},
        {"key": "disposal_gain_loss", "label": "Disposal Gain/Loss"}, {"key": "net_profit", "label": "Net Profit"},
        {"key": "total_investor_share_amount", "label": "Investor Share"}, {"key": "owner_share_amount", "label": "Owner Share"},
    ]
    queryset_fn       = staticmethod(get_net_profit_report_queryset)
    stats_fn          = staticmethod(get_net_profit_report_stats)
    stats_all_time_fn = staticmethod(get_net_profit_report_stats_all_time)
    serializer_class  = NetProfitReportItemSerializer


class AssetDepreciationReportPrintView(BaseReportPrintView):
    title             = "Asset Depreciation Report"
    columns           = [
        {"key": "asset_name", "label": "Asset"}, {"key": "category_name", "label": "Category"},
        {"key": "period", "label": "For Month"}, {"key": "rate_applied", "label": "Rate"},
        {"key": "worth_before", "label": "Worth Before"}, {"key": "worth_after", "label": "Worth After"},
        {"key": "amount", "label": "Depreciation"}, {"key": "created_at", "label": "Posted On"},
    ]
    queryset_fn       = staticmethod(get_asset_depreciation_report_queryset)
    stats_fn          = staticmethod(get_asset_depreciation_report_stats)
    stats_all_time_fn = staticmethod(get_asset_depreciation_report_stats_all_time)
    serializer_class  = AssetDepreciationReportItemSerializer


class InventoryValuationReportPrintView(APIView):
    """
    GET /reports/inventory-valuation/print/?search=
    Live snapshot, no date filter — same shape as the on-screen report.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        search = request.query_params.get("search")
        rows_data = get_inventory_valuation_report_data(search=search)
        stats = get_inventory_valuation_report_stats(rows_data)
        rows = InventoryValuationReportItemSerializer(rows_data, many=True).data

        filter_description = f"Search: {search}" if search else "All products currently in stock"

        pdf_bytes, filename = generate_report_pdf_bytes(
            title="Inventory Valuation Report",
            filter_description=filter_description,
            columns=[
                {"key": "product_name", "label": "Product"}, {"key": "product_code", "label": "Code"},
                {"key": "category_name", "label": "Category"}, {"key": "quantity_on_hand", "label": "Qty on Hand"},
                {"key": "avg_unit_cost", "label": "Avg Unit Cost"}, {"key": "total_value", "label": "Total Value"},
            ],
            rows=rows,
            stats=[{"label": _humanize(k), "value": v} for k, v in stats.items()],
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class StockMovementReportPrintView(APIView):
    """
    GET /reports/stock-movement/print/?date=&date_from=&date_to=&search=
    Rows are grouped across 4 source tables (not a single queryset), and
    this report uniquely combines a date filter with a search box — doesn't
    fit BaseReportPrintView's single-queryset_fn shape, so it's written
    directly here (same as InventoryValuationReportPrintView above).
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        filters_serializer = ReportDateFilterSerializer(data=request.query_params)
        filters_serializer.is_valid(raise_exception=True)
        filters = filters_serializer.validated_data
        search = request.query_params.get("search")

        rows_data = get_stock_movement_report_rows(**filters, search=search)

        if _has_date_filter(request) or (search and search.strip()):
            stats = get_stock_movement_report_stats(rows_data)
        else:
            stats = get_stock_movement_report_stats_all_time()

        rows = StockMovementReportItemSerializer(rows_data, many=True).data

        filter_description = _describe_filters(request.query_params)
        if search:
            filter_description += f" — Search: {search}"

        pdf_bytes, filename = generate_report_pdf_bytes(
            title="Stock Movement Report",
            filter_description=filter_description,
            columns=[
                {"key": "product_name", "label": "Product"}, {"key": "product_code", "label": "Code"},
                {"key": "total_purchased", "label": "Purchased"}, {"key": "total_purchase_returned", "label": "Purchase Returned"},
                {"key": "total_sold", "label": "Sold"}, {"key": "total_sale_returned", "label": "Sale Returned"},
                {"key": "total_lost", "label": "Lost"}, {"key": "total_found", "label": "Found"},
            ],
            rows=rows,
            stats=[{"label": _humanize(k), "value": v} for k, v in stats.items()],
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response
