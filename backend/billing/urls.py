from django.urls import path

from .views import (
    AllInvoicePaymentsView,
    AllOutstandingInvoicesView,
    ConfirmedInvoiceListView,
    CustomerListCreateView,
    CustomerOutstandingListView,
    CustomerOutstandingView,
    CustomerRetrieveUpdateDestroyView,
    DraftInvoiceListView,
    DueInvoiceListView,
    InvoiceConfirmView,
    InvoiceCandidateShelvesView,
    InvoiceAutoAllocateShelvesView,
    InvoiceDueDateUpdateView,
    InvoiceFilteredListView,
    InvoiceListCreateView,
    InvoicePaymentSummaryView,
    InvoicePrintView,
    InvoiceRetrieveUpdateDestroyView,
    InvoiceSavedPDFListView,
    InvoiceSavePDFView,
    PaymentDestroyView,
    PaymentListCreateView,
    ReturnAcceptView,
    ReturnListCreateView,
    ReturnRetrieveUpdateDestroyView,
    AllReturnsView,
    SavedPDFDeleteView,
    SetInvoiceItemShelfAllocationsView,
    SetReturnItemShelfAllocationsView,
)

urlpatterns = [
    # Customers
    path("customers/", CustomerListCreateView.as_view(), name="customer-list-create"),
    path("customers/<int:pk>/", CustomerRetrieveUpdateDestroyView.as_view(), name="customer-detail"),

    # Invoices
    path("invoices/", InvoiceListCreateView.as_view(), name="invoice-list-create"),
    path("invoices/drafts/", DraftInvoiceListView.as_view(), name="invoice-drafts"),
    path("invoices/due/", DueInvoiceListView.as_view(), name="invoice-due"),
    path("invoices/<int:pk>/", InvoiceRetrieveUpdateDestroyView.as_view(), name="invoice-detail"),
    path("invoices/<int:pk>/confirm/", InvoiceConfirmView.as_view(), name="invoice-confirm"),
    path("invoices/<int:pk>/due-date/", InvoiceDueDateUpdateView.as_view(), name="invoice-due-date-update"),

    # Payments (nested under invoice)
    path("invoices/<int:invoice_id>/payments/", PaymentListCreateView.as_view(), name="payment-list-create"),
    path("payments/", AllInvoicePaymentsView.as_view(), name="payment-list-all"),
    path("payments/<int:pk>/", PaymentDestroyView.as_view(), name="payment-delete"),

    # Returns (nested under invoice + standalone accept)
    path("invoices/<int:invoice_id>/returns/", ReturnListCreateView.as_view(), name="return-list-create"),
    path("returns/", AllReturnsView.as_view(), name="return-list-all"),
    path("returns/<int:pk>/accept/", ReturnAcceptView.as_view(), name="return-accept"),
    path("returns/<int:pk>/", ReturnRetrieveUpdateDestroyView.as_view(), name="return-detail"),

    # Payment summaries
    path("invoices/<int:pk>/payment-summary/", InvoicePaymentSummaryView.as_view(), name="invoice-payment-summary"),
    path("customers/outstanding/", CustomerOutstandingListView.as_view(), name="customer-outstanding-list"),
    path("customers/<int:pk>/outstanding/", CustomerOutstandingView.as_view(), name="customer-outstanding"),

    # Confirmed invoices (dedicated endpoint)
    path("invoices/confirmed/", ConfirmedInvoiceListView.as_view(), name="invoice-confirmed-list"),
    path("invoices/outstanding/", AllOutstandingInvoicesView.as_view(), name="invoice-outstanding-list"),

    # Master filter search
    path("invoices/search/", InvoiceFilteredListView.as_view(), name="invoice-search"),

    # PDF - print (no save)
    path("invoices/<int:pk>/print/", InvoicePrintView.as_view(), name="invoice-print"),

    # PDF - save to disk + list saved PDFs
    path("invoices/<int:pk>/pdf/save/", InvoiceSavePDFView.as_view(), name="invoice-pdf-save"),
    path("invoices/<int:pk>/pdf/", InvoiceSavedPDFListView.as_view(), name="invoice-pdf-list"),

    # Delete a saved PDF
    path("pdf/<int:saved_pdf_id>/", SavedPDFDeleteView.as_view(), name="pdf-delete"),

    # Shelf allocations — sale line consumption / return line put-away
    path("shelves/candidates/", InvoiceCandidateShelvesView.as_view(), name="invoice-candidate-shelves"),
    path("shelves/auto-allocate/", InvoiceAutoAllocateShelvesView.as_view(), name="invoice-shelf-auto-allocate"),
    path("invoice-items/<int:pk>/shelf-allocations/", SetInvoiceItemShelfAllocationsView.as_view(), name="invoice-item-shelf-allocations"),
    path("return-items/<int:pk>/shelf-allocations/", SetReturnItemShelfAllocationsView.as_view(), name="return-item-shelf-allocations"),
]