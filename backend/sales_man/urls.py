from django.urls import path

from .views import (
    SalesManCustomerListView,
    SalesManInvoiceListView,
    SalesManLinkNameDestroyView,
    SalesManLinkNameListCreateView,
    SalesManLinkNameOptionsView,
    SalesManListCreateView,
    SalesManRetrieveUpdateDestroyView,
)

urlpatterns = [
    path("sales-men/", SalesManListCreateView.as_view(), name="sales-man-list-create"),
    path("sales-men/<int:pk>/", SalesManRetrieveUpdateDestroyView.as_view(), name="sales-man-detail"),

    path("sales-men/<int:sales_man_id>/link-names/", SalesManLinkNameListCreateView.as_view(), name="sales-man-link-name-list-create"),
    # IMPORTANT: static path before the dynamic <int:pk>/ path below.
    path("link-names/", SalesManLinkNameOptionsView.as_view(), name="sales-man-link-name-options"),
    path("link-names/<int:pk>/", SalesManLinkNameDestroyView.as_view(), name="sales-man-link-name-delete"),

    path("sales-men/<int:sales_man_id>/customers/", SalesManCustomerListView.as_view(), name="sales-man-customers"),
    path("sales-men/<int:sales_man_id>/invoices/", SalesManInvoiceListView.as_view(), name="sales-man-invoices"),
]
