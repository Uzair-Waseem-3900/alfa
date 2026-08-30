from django.urls import path

from .views import (
    CashFlowStatsView,
    CashInHandBreakdownView,
    CustomerOutstandingBreakdownView,
    CustomerReturnsBreakdownView,
    ExpenseCategoryListCreateView,
    ExpenseCategoryRetrieveUpdateDestroyView,
    ExpenseListCreateView,
    ExpenseRetrieveUpdateDestroyView,
    ExpensesBreakdownView,
    GrossProfitTrendView,
    InvoicesBreakdownView,
    LostInventoryBreakdownView,
    OpeningClosingCashView,
    ProfitBreakdownView,
    PurchaseReturnsBreakdownView,
    PurchasesBreakdownView,
    SupplierOutstandingBreakdownView,
    TotalInvoicesCashBreakdownView,
    TotalPaidPayablesBreakdownView,
)

urlpatterns = [
    # Dashboard stats (all 10 numbers)
    path("stats/", CashFlowStatsView.as_view(), name="cashflow-stats"),

    # Expense categories
    path("expense-categories/",          ExpenseCategoryListCreateView.as_view(),          name="expense-category-list-create"),
    path("expense-categories/<int:pk>/", ExpenseCategoryRetrieveUpdateDestroyView.as_view(), name="expense-category-detail"),

    # Expenses
    path("expenses/",          ExpenseListCreateView.as_view(),          name="expense-list-create"),
    path("expenses/<int:pk>/", ExpenseRetrieveUpdateDestroyView.as_view(), name="expense-detail"),

    # Breakdown drill-down endpoints
    path("breakdown/cash-in-hand/",         CashInHandBreakdownView.as_view(),          name="breakdown-cash-in-hand"),
    path("breakdown/cash-in-hand/opening-closing/", OpeningClosingCashView.as_view(),   name="breakdown-cash-in-hand-opening-closing"),
    path("breakdown/invoices-cash/",        TotalInvoicesCashBreakdownView.as_view(),   name="breakdown-invoices-cash"),
    path("breakdown/customer-outstanding/", CustomerOutstandingBreakdownView.as_view(), name="breakdown-customer-outstanding"),
    path("breakdown/paid-payables/",        TotalPaidPayablesBreakdownView.as_view(),   name="breakdown-paid-payables"),
    path("breakdown/supplier-outstanding/", SupplierOutstandingBreakdownView.as_view(), name="breakdown-supplier-outstanding"),
    path("breakdown/invoices/",             InvoicesBreakdownView.as_view(),            name="breakdown-invoices"),
    path("breakdown/purchases/",            PurchasesBreakdownView.as_view(),           name="breakdown-purchases"),
    path("breakdown/expenses/",             ExpensesBreakdownView.as_view(),            name="breakdown-expenses"),
    path("breakdown/lost-inventory/",       LostInventoryBreakdownView.as_view(),       name="breakdown-lost-inventory"),
    path("breakdown/purchase-returns/",     PurchaseReturnsBreakdownView.as_view(),     name="breakdown-purchase-returns"),
    path("breakdown/customer-returns/",     CustomerReturnsBreakdownView.as_view(),     name="breakdown-customer-returns"),
    path("breakdown/profit/",               ProfitBreakdownView.as_view(),              name="breakdown-profit"),

    # Dashboard graph
    path("gross-profit-trend/", GrossProfitTrendView.as_view(), name="gross-profit-trend"),
]