from django.urls import path

from .views import (
    CustomerLedgerByCustomerView,
    CustomerLedgerDetailView,
    CustomerLedgerListView,
    CustomerLedgerPrintView,
    CustomerLedgerSavedPDFDeleteView,
    CustomerLedgerSavedPDFListView,
    CustomerLedgerSavePDFView,
    LedgerPrintView,
    LedgerSavedPDFDeleteView,
    LedgerSavedPDFListView,
    LedgerSavePDFView,
    SupplierLedgerBySupplierView,
    SupplierLedgerDetailView,
    SupplierLedgerListView,
)

urlpatterns = [
    # -- Customer ledger routes (declared first — "customers/" would
    #    otherwise be swallowed by the supplier "<int:pk>/" pattern below) --
    path("customers/", CustomerLedgerListView.as_view(), name="customer-ledger-list"),
    path("customers/by-customer/<int:customer_id>/", CustomerLedgerByCustomerView.as_view(), name="customer-ledger-by-customer"),
    path("customers/pdf/<int:saved_pdf_id>/", CustomerLedgerSavedPDFDeleteView.as_view(), name="customer-ledger-pdf-delete"),
    path("customers/<int:pk>/", CustomerLedgerDetailView.as_view(), name="customer-ledger-detail"),
    path("customers/<int:pk>/print/", CustomerLedgerPrintView.as_view(), name="customer-ledger-print"),
    path("customers/<int:pk>/pdf/save/", CustomerLedgerSavePDFView.as_view(), name="customer-ledger-pdf-save"),
    path("customers/<int:pk>/pdf/", CustomerLedgerSavedPDFListView.as_view(), name="customer-ledger-pdf-list"),

    # List all ledgers
    path("", SupplierLedgerListView.as_view(), name="ledger-list"),

    # Ledger by ledger id
    path("<int:pk>/", SupplierLedgerDetailView.as_view(), name="ledger-detail"),

    # Ledger by supplier id (convenience)
    path("supplier/<int:supplier_id>/", SupplierLedgerBySupplierView.as_view(), name="ledger-by-supplier"),

    # PDF — print (stream, no save)
    path("<int:pk>/print/", LedgerPrintView.as_view(), name="ledger-print"),

    # PDF — save to disk
    path("<int:pk>/pdf/save/", LedgerSavePDFView.as_view(), name="ledger-pdf-save"),

    # PDF — list saved
    path("<int:pk>/pdf/", LedgerSavedPDFListView.as_view(), name="ledger-pdf-list"),

    # PDF — delete saved
    path("pdf/<int:saved_pdf_id>/", LedgerSavedPDFDeleteView.as_view(), name="ledger-pdf-delete"),
]