from django.urls import path

from .views import (
    CreditCustomerReportView,
    CustomerCreditScoreDetailView,
    CustomerCreditScoreHistoryView,
)

urlpatterns = [
    path("customers/", CreditCustomerReportView.as_view(), name="credit-customer-report"),
    path("customers/<int:customer_id>/", CustomerCreditScoreDetailView.as_view(), name="credit-score-detail"),
    path("customers/<int:customer_id>/history/", CustomerCreditScoreHistoryView.as_view(), name="credit-score-history"),
]
