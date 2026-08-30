from django.urls import path

from .views import (
    APAgingListView,
    APAgingPrintView,
    ARAgingListView,
    ARAgingPrintView,
    BalanceSheetPrintView,
    BalanceSheetView,
    CashFlowStatementPrintView,
    CashFlowStatementView,
    FixedAssetRegisterListView,
    FixedAssetRegisterPrintView,
    IncomeStatementPrintView,
    IncomeStatementView,
)

urlpatterns = [
    path("ar-aging/", ARAgingListView.as_view(), name="ar-aging-list"),
    path("ar-aging/print/", ARAgingPrintView.as_view(), name="ar-aging-print"),

    path("ap-aging/", APAgingListView.as_view(), name="ap-aging-list"),
    path("ap-aging/print/", APAgingPrintView.as_view(), name="ap-aging-print"),

    path("fixed-asset-register/", FixedAssetRegisterListView.as_view(), name="fixed-asset-register-list"),
    path("fixed-asset-register/print/", FixedAssetRegisterPrintView.as_view(), name="fixed-asset-register-print"),

    path("cash-flow-statement/", CashFlowStatementView.as_view(), name="cash-flow-statement"),
    path("cash-flow-statement/print/", CashFlowStatementPrintView.as_view(), name="cash-flow-statement-print"),

    path("income-statement/", IncomeStatementView.as_view(), name="income-statement"),
    path("income-statement/print/", IncomeStatementPrintView.as_view(), name="income-statement-print"),

    path("balance-sheet/", BalanceSheetView.as_view(), name="balance-sheet"),
    path("balance-sheet/print/", BalanceSheetPrintView.as_view(), name="balance-sheet-print"),
]
