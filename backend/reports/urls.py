from django.urls import path

from .views import (
    AssetDepreciationReportPrintView,
    AssetDepreciationReportView,
    CashCollectedReportPrintView,
    CashCollectedReportView,
    CustomerReturnsReportPrintView,
    CustomerReturnsReportView,
    ExpensesReportPrintView,
    ExpensesReportView,
    InputTaxReportPrintView,
    InputTaxReportView,
    InventoryValuationReportPrintView,
    InventoryValuationReportView,
    InvoicesReportPrintView,
    InvoicesReportView,
    LostInventoryReportPrintView,
    LostInventoryReportView,
    NetProfitReportPrintView,
    NetProfitReportView,
    OutputTaxReportPrintView,
    OutputTaxReportView,
    ProfitMarginReportPrintView,
    ProfitMarginReportView,
    PurchaseReturnsReportPrintView,
    PurchaseReturnsReportView,
    RecurringExpensesReportPrintView,
    RecurringExpensesReportView,
    StockMovementReportPrintView,
    StockMovementReportView,
)

urlpatterns = [
    path("invoices/", InvoicesReportView.as_view(), name="report-invoices"),
    path("invoices/print/", InvoicesReportPrintView.as_view(), name="report-invoices-print"),

    path("cash-collected/", CashCollectedReportView.as_view(), name="report-cash-collected"),
    path("cash-collected/print/", CashCollectedReportPrintView.as_view(), name="report-cash-collected-print"),

    path("expenses/", ExpensesReportView.as_view(), name="report-expenses"),
    path("expenses/print/", ExpensesReportPrintView.as_view(), name="report-expenses-print"),

    path("lost-inventory/", LostInventoryReportView.as_view(), name="report-lost-inventory"),
    path("lost-inventory/print/", LostInventoryReportPrintView.as_view(), name="report-lost-inventory-print"),

    path("purchase-returns/", PurchaseReturnsReportView.as_view(), name="report-purchase-returns"),
    path("purchase-returns/print/", PurchaseReturnsReportPrintView.as_view(), name="report-purchase-returns-print"),

    path("customer-returns/", CustomerReturnsReportView.as_view(), name="report-customer-returns"),
    path("customer-returns/print/", CustomerReturnsReportPrintView.as_view(), name="report-customer-returns-print"),

    path("profit-margin/", ProfitMarginReportView.as_view(), name="report-profit-margin"),
    path("profit-margin/print/", ProfitMarginReportPrintView.as_view(), name="report-profit-margin-print"),

    path("inventory-valuation/", InventoryValuationReportView.as_view(), name="report-inventory-valuation"),
    path("inventory-valuation/print/", InventoryValuationReportPrintView.as_view(), name="report-inventory-valuation-print"),

    path("sales-tax/input/", InputTaxReportView.as_view(), name="report-sales-tax-input"),
    path("sales-tax/input/print/", InputTaxReportPrintView.as_view(), name="report-sales-tax-input-print"),

    path("sales-tax/output/", OutputTaxReportView.as_view(), name="report-sales-tax-output"),
    path("sales-tax/output/print/", OutputTaxReportPrintView.as_view(), name="report-sales-tax-output-print"),

    path("recurring-expenses/", RecurringExpensesReportView.as_view(), name="report-recurring-expenses"),
    path("recurring-expenses/print/", RecurringExpensesReportPrintView.as_view(), name="report-recurring-expenses-print"),

    path("net-profit/", NetProfitReportView.as_view(), name="report-net-profit"),
    path("net-profit/print/", NetProfitReportPrintView.as_view(), name="report-net-profit-print"),

    path("asset-depreciation/", AssetDepreciationReportView.as_view(), name="report-asset-depreciation"),
    path("asset-depreciation/print/", AssetDepreciationReportPrintView.as_view(), name="report-asset-depreciation-print"),

    path("stock-movement/", StockMovementReportView.as_view(), name="report-stock-movement"),
    path("stock-movement/print/", StockMovementReportPrintView.as_view(), name="report-stock-movement-print"),
]
