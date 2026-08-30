from django.urls import path

from .views import (
    TaxPaymentListCreateView,
    TaxPaymentRetrieveDestroyView,
    TaxStatsView,
    WHTPaymentListCreateView,
    WHTPaymentRetrieveDestroyView,
)

urlpatterns = [
    path("stats/", TaxStatsView.as_view(), name="tax-stats"),

    path("payments/",      TaxPaymentListCreateView.as_view(),     name="tax-payment-list-create"),
    path("payments/<int:pk>/", TaxPaymentRetrieveDestroyView.as_view(), name="tax-payment-detail"),

    path("wht-payments/",      WHTPaymentListCreateView.as_view(),     name="wht-payment-list-create"),
    path("wht-payments/<int:pk>/", WHTPaymentRetrieveDestroyView.as_view(), name="wht-payment-detail"),
]
