from django.urls import path

from .views import (
    ProductRateHistoryView,
    ProductRateListCreateView,
    ProductRateRetrieveUpdateView,
    RateListPrintView,
    UnpricedProductListView,
)

urlpatterns = [
    # Current rates — list + create
    path("", ProductRateListCreateView.as_view(), name="rate-list-create"),

    # Print current rates (respects the same filters as the list)
    path("print/", RateListPrintView.as_view(), name="rate-list-print"),

    # Products with no rate set yet
    path("unpriced/", UnpricedProductListView.as_view(), name="rate-unpriced-products"),

    # Single rate — retrieve + update price
    path("<int:pk>/", ProductRateRetrieveUpdateView.as_view(), name="rate-detail"),

    # Full price history for a product
    path("history/<int:product_id>/", ProductRateHistoryView.as_view(), name="rate-history"),
]