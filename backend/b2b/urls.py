from django.urls import path

from .views import ProviderListView, ProviderRateListView, ProviderRequestView

urlpatterns = [
    path("providers/", ProviderListView.as_view(), name="b2b-provider-list"),
    path("providers/<str:provider>/rate-list/", ProviderRateListView.as_view(), name="b2b-provider-rate-list"),
    path("providers/<str:provider>/request/", ProviderRequestView.as_view(), name="b2b-provider-request"),
]
