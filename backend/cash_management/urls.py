from django.urls import path

from .views import (
    CashAdjustmentListCreateView,
    CashAdjustmentRetrieveDestroyView,
    CashManagementStatsView,
    InvestorListCreateView,
    InvestorRetrieveUpdateDestroyView,
    InvestorTransactionListCreateView,
    InvestorTransactionRetrieveDestroyView,
    InvestorValuationEntryListView,
    OwnerTransactionListCreateView,
    OwnerTransactionRetrieveDestroyView,
)

urlpatterns = [
    path("stats/", CashManagementStatsView.as_view(), name="cash-management-stats"),

    path("adjustments/",      CashAdjustmentListCreateView.as_view(),     name="cash-adjustment-list-create"),
    path("adjustments/<int:pk>/", CashAdjustmentRetrieveDestroyView.as_view(), name="cash-adjustment-detail"),

    # IMPORTANT: static paths (valuation-entries/) before dynamic <int:pk>/ paths
    path("investors/valuation-entries/", InvestorValuationEntryListView.as_view(), name="investor-valuation-entry-list"),

    path("investors/",      InvestorListCreateView.as_view(),           name="investor-list-create"),
    path("investors/<int:pk>/", InvestorRetrieveUpdateDestroyView.as_view(), name="investor-detail"),

    path("investor-transactions/",      InvestorTransactionListCreateView.as_view(),     name="investor-transaction-list-create"),
    path("investor-transactions/<int:pk>/", InvestorTransactionRetrieveDestroyView.as_view(), name="investor-transaction-detail"),

    path("owner-transactions/",      OwnerTransactionListCreateView.as_view(),     name="owner-transaction-list-create"),
    path("owner-transactions/<int:pk>/", OwnerTransactionRetrieveDestroyView.as_view(), name="owner-transaction-detail"),
]
