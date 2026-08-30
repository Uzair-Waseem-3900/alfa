from django.urls import path

from .views import (
    AccountTransferListCreateView,
    AccountTransferRetrieveDestroyView,
    PaymentMethodAllocationListView,
    PaymentMethodListCreateView,
    PaymentMethodRetrieveUpdateDestroyView,
)

urlpatterns = [
    # IMPORTANT: static "transfers/" path before dynamic "<int:pk>/" paths.
    path("transfers/", AccountTransferListCreateView.as_view(), name="account-transfer-list-create"),
    path("transfers/<int:pk>/", AccountTransferRetrieveDestroyView.as_view(), name="account-transfer-detail"),

    path("", PaymentMethodListCreateView.as_view(), name="payment-method-list-create"),
    path("<int:pk>/", PaymentMethodRetrieveUpdateDestroyView.as_view(), name="payment-method-detail"),
    path("<int:pk>/allocations/", PaymentMethodAllocationListView.as_view(), name="payment-method-allocations"),
]
