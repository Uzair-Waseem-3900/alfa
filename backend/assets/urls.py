from django.urls import path

from .views import (
    AssetCategoryListCreateView,
    AssetCategoryRetrieveUpdateView,
    AssetDisposalListView,
    AssetDisposeView,
    AssetListCreateView,
    AssetPaymentListView,
    AssetPaymentRetrieveView,
    AssetRetrieveView,
    AssetRevalueView,
    AssetStatsView,
    AssetValuationEntryListView,
)

urlpatterns = [
    path("stats/", AssetStatsView.as_view(), name="asset-stats"),

    path("categories/",      AssetCategoryListCreateView.as_view(),      name="asset-category-list-create"),
    path("categories/<int:pk>/", AssetCategoryRetrieveUpdateView.as_view(), name="asset-category-detail"),

    # IMPORTANT: static paths before dynamic <int:pk>/ paths
    path("items/valuation-entries/", AssetValuationEntryListView.as_view(), name="asset-valuation-entry-list"),

    path("items/",      AssetListCreateView.as_view(),     name="asset-list-create"),
    path("items/<int:pk>/", AssetRetrieveView.as_view(),       name="asset-detail"),
    path("items/<int:pk>/revalue/", AssetRevalueView.as_view(), name="asset-revalue"),
    path("items/<int:pk>/dispose/", AssetDisposeView.as_view(), name="asset-dispose"),

    path("disposals/", AssetDisposalListView.as_view(), name="asset-disposal-list"),

    path("payments/", AssetPaymentListView.as_view(), name="asset-payment-list"),
    path("payments/<int:pk>/", AssetPaymentRetrieveView.as_view(), name="asset-payment-detail"),
]
