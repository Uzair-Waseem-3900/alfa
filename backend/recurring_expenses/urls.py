from django.urls import path

from .views import (
    RecurringExpenseAssignmentBulkCreateView,
    RecurringExpenseAssignmentListCreateView,
    RecurringExpenseAssignmentPaymentListCreateView,
    RecurringExpenseAssignmentPaymentRetrieveDestroyView,
    RecurringExpenseAssignmentRetrieveDestroyView,
    RecurringExpenseCategoryListCreateView,
    RecurringExpenseCategoryRetrieveUpdateDestroyView,
    RecurringExpenseFlowStatsView,
    RecurringExpenseListCreateView,
    RecurringExpenseMonthlyStatsDetailView,
    RecurringExpenseMonthlyStatsListView,
    RecurringExpensePendingDuesView,
    RecurringExpenseRetrieveUpdateDestroyView,
)

urlpatterns = [
    path("stats/flow/",    RecurringExpenseFlowStatsView.as_view(),    name="recurring-expense-flow-stats"),
    path("stats/monthly/", RecurringExpenseMonthlyStatsListView.as_view(), name="recurring-expense-monthly-stats-list"),
    path("stats/monthly/<str:period>/", RecurringExpenseMonthlyStatsDetailView.as_view(), name="recurring-expense-monthly-stats-detail"),

    path("categories/",      RecurringExpenseCategoryListCreateView.as_view(),           name="recurring-expense-category-list-create"),
    path("categories/<int:pk>/", RecurringExpenseCategoryRetrieveUpdateDestroyView.as_view(), name="recurring-expense-category-detail"),

    # IMPORTANT: static paths before dynamic <int:pk>/ paths
    path("templates/pending-dues/", RecurringExpensePendingDuesView.as_view(), name="recurring-expense-pending-dues"),
    path("templates/",      RecurringExpenseListCreateView.as_view(),           name="recurring-expense-list-create"),
    path("templates/<int:pk>/", RecurringExpenseRetrieveUpdateDestroyView.as_view(), name="recurring-expense-detail"),

    path("assignments/bulk/", RecurringExpenseAssignmentBulkCreateView.as_view(), name="recurring-expense-assignment-bulk-create"),
    path("assignments/",      RecurringExpenseAssignmentListCreateView.as_view(), name="recurring-expense-assignment-list-create"),
    path("assignments/<int:pk>/", RecurringExpenseAssignmentRetrieveDestroyView.as_view(), name="recurring-expense-assignment-detail"),

    path("payments/",      RecurringExpenseAssignmentPaymentListCreateView.as_view(),     name="recurring-expense-payment-list-create"),
    path("payments/<int:pk>/", RecurringExpenseAssignmentPaymentRetrieveDestroyView.as_view(), name="recurring-expense-payment-detail"),
]
