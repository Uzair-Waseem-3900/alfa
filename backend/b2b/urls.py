from django.urls import path

from .request_views import (
    PartnerDecidedView,
    ProviderProductSearchView,
    PurchaseRequestCancelView,
    PurchaseRequestDetailView,
    PurchaseRequestListCreateView,
    PurchaseRequestSyncView,
)
from .views import ProviderListView, ProviderRateListView, ProviderRequestView

urlpatterns = [
    path("providers/", ProviderListView.as_view(), name="b2b-provider-list"),
    path("providers/<str:provider>/rate-list/", ProviderRateListView.as_view(), name="b2b-provider-rate-list"),
    path("providers/<str:provider>/request/", ProviderRequestView.as_view(), name="b2b-provider-request"),
    path("providers/<str:provider>/products/", ProviderProductSearchView.as_view(), name="b2b-provider-products"),

    path("purchase-requests/", PurchaseRequestListCreateView.as_view(), name="b2b-purchase-request-list"),
    path("purchase-requests/sync/", PurchaseRequestSyncView.as_view(), name="b2b-purchase-request-sync"),
    path("purchase-requests/<int:pk>/", PurchaseRequestDetailView.as_view(), name="b2b-purchase-request-detail"),
    path("purchase-requests/<int:pk>/cancel/", PurchaseRequestCancelView.as_view(), name="b2b-purchase-request-cancel"),

    # Called by a partner software (signed), never by a browser
    path("partner/purchase-requests/decided/", PartnerDecidedView.as_view(), name="b2b-partner-decided"),
]
