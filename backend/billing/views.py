from rest_framework import generics, status
from rest_framework.response import Response

from payment_methods.mixins import AllocationsListMixin

from .models import Invoice
from .permissions import IsAdminOrSuperuser, IsAdminOrSuperuserOrReadOnly, IsAuthenticated
from .selectors import (
    get_all_customers,
    get_customer_by_id,
    get_filtered_invoices,
    get_invoice_by_id,
    get_invoice_item_with_allocations_by_id,
    get_payment_by_id,
    get_payments_for_invoice,
    get_return_by_id,
    get_return_item_by_id,
    get_returns_for_invoice,
    get_all_returns,
)
from .serializers import (
    AutoAllocateShelvesRequestSerializer, AutoAllocateShelvesResponseSerializer,
    CandidateShelfSerializer,
    CustomerReadSerializer,
    CustomerWriteSerializer,
    InvoiceCreateSerializer,
    InvoiceDueDateUpdateSerializer,
    InvoiceItemReadSerializer,
    InvoiceReadSerializer,
    InvoiceUpdateSerializer,
    PaymentReadSerializer,
    PaymentWriteSerializer,
    ReturnCreateSerializer,
    ReturnItemReadSerializer,
    ReturnReadSerializer,
    ReturnUpdateSerializer,
    SetShelfAllocationsSerializer,
)
from .services import (
    accept_return,
    cancel_return,
    confirm_invoice,
    create_customer,
    create_invoice,
    create_payment,
    create_return,
    delete_customer,
    delete_invoice,
    delete_payment,
    set_invoice_item_shelf_allocations,
    set_return_item_shelf_allocations,
    update_customer,
    update_invoice_due_date,
    update_invoice_items,
    update_return_items,
)


def _as_splits(method_allocations):
    """MethodAllocationInputSerializer's validated_data is a list of
    {"payment_method": <PaymentMethod>, "amount": Decimal} dicts — services
    take [(payment_method, amount), ...] tuples, the shape
    payment_methods.services.record_allocations expects."""
    if not method_allocations:
        return None
    return [(d["payment_method"], d["amount"]) for d in method_allocations]


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class CustomerListCreateView(generics.ListCreateAPIView):
    """
    GET  /billing/customers/       — list all customers
                                      (search: ?search= across name/code/mobile,
                                      or narrow with ?name= / ?code= individually)
    POST /billing/customers/       — create customer (all authenticated)
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return CustomerWriteSerializer if self.request.method == "POST" else CustomerReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_customers(
            search=p.get("search"), name=p.get("name"), code=p.get("code"),
            tier=p.get("tier"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        customer = create_customer(
            name=d["name"], code=d["code"],
            address=d["address"], mobile=d.get("mobile", ""),
            user=request.user,
        )
        return Response(CustomerReadSerializer(customer).data, status=status.HTTP_201_CREATED)


class CustomerRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /billing/customers/<pk>/
    PATCH  /billing/customers/<pk>/
    DELETE /billing/customers/<pk>/
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return CustomerWriteSerializer if self.request.method == "PATCH" else CustomerReadSerializer

    def get_object(self):
        return get_customer_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        customer = update_customer(pk=self.kwargs["pk"], user=request.user, **serializer.validated_data)
        return Response(CustomerReadSerializer(customer).data)

    def destroy(self, request, *args, **kwargs):
        delete_customer(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Customer deleted."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Invoice — list + create
# ---------------------------------------------------------------------------

class InvoiceListCreateView(generics.ListCreateAPIView):
    """
    GET  /billing/invoices/         — all invoices, full filter set (see get_filtered_invoices)
                                       plus ?customer_id= for an exact-match lookup
    POST /billing/invoices/         — create draft (all authenticated)
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return InvoiceCreateSerializer if self.request.method == "POST" else InvoiceReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_filtered_invoices(
            status         = p.get("status"),
            customer_id    = p.get("customer_id"),
            customer_name  = p.get("customer_name"),
            customer_code  = p.get("customer_code"),
            bill_number    = p.get("bill_number"),
            date           = p.get("date"),
            date_from      = p.get("date_from"),
            date_to        = p.get("date_to"),
            payment_status = p.get("payment_status"),
            min_amount     = p.get("min_amount"),
            max_amount     = p.get("max_amount"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        invoice = create_invoice(
            customer_id=d["customer_id"],
            items=d["items"],
            payment_type=d.get("payment_type", "after_delivery"),
            advance_amount=d.get("advance_amount", 0),
            method_allocations=_as_splits(d.get("method_allocations")),
            payment_due_date=d.get("payment_due_date"),
            user=request.user,
        )
        # Re-fetch through the selector that carries the prefetches
        # InvoiceReadSerializer's nested shelf_allocations field needs —
        # the bare instance create_invoice() built has no prefetch cache,
        # which would N+1 (product + shelf_allocations per item) here.
        invoice = get_invoice_by_id(invoice.id)
        return Response(InvoiceReadSerializer(invoice, context={"request": request}).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Draft invoices — separate endpoint as per instructions
# ---------------------------------------------------------------------------

class DraftInvoiceListView(generics.ListAPIView):
    """
    GET /billing/invoices/drafts/   — draft invoices, full filter set (see get_filtered_invoices)
    """
    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_filtered_invoices(
            status         = Invoice.Status.DRAFT,
            customer_id    = p.get("customer_id"),
            customer_name  = p.get("customer_name"),
            customer_code  = p.get("customer_code"),
            bill_number    = p.get("bill_number"),
            date           = p.get("date"),
            date_from      = p.get("date_from"),
            date_to        = p.get("date_to"),
            payment_status = p.get("payment_status"),
            min_amount     = p.get("min_amount"),
            max_amount     = p.get("max_amount"),
        )


# ---------------------------------------------------------------------------
# Due invoices — confirmed, still-outstanding, past their due date
# ---------------------------------------------------------------------------

class DueInvoiceListView(generics.ListAPIView):
    """
    GET /billing/invoices/due/   — invoices whose due date has passed, full
    filter set (see get_filtered_invoices). Always computed live from
    payment_due_date <= today — no stale state, correct on every request
    regardless of how long since the tab was last opened.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = InvoiceReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_filtered_invoices(
            due_only       = True,
            customer_id    = p.get("customer_id"),
            customer_name  = p.get("customer_name"),
            customer_code  = p.get("customer_code"),
            bill_number    = p.get("bill_number"),
            date           = p.get("date"),
            date_from      = p.get("date_from"),
            date_to        = p.get("date_to"),
            payment_status = p.get("payment_status"),
            min_amount     = p.get("min_amount"),
            max_amount     = p.get("max_amount"),
        )


# ---------------------------------------------------------------------------
# Invoice — retrieve + update + delete
# ---------------------------------------------------------------------------

class InvoiceRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /billing/invoices/<pk>/  — anyone authenticated
    PATCH  /billing/invoices/<pk>/  — update items on DRAFT only (anyone)
    DELETE /billing/invoices/<pk>/  — soft delete DRAFT only (anyone)
    """
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return InvoiceUpdateSerializer if self.request.method == "PATCH" else InvoiceReadSerializer

    def get_object(self):
        return get_invoice_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = update_invoice_items(
            invoice_id=self.kwargs["pk"],
            items=serializer.validated_data["items"],
            payment_type=serializer.validated_data.get("payment_type"),
            advance_amount=serializer.validated_data.get("advance_amount"),
            method_allocations=_as_splits(serializer.validated_data.get("method_allocations")),
            payment_due_date=serializer.validated_data.get("payment_due_date"),
            user=request.user,
        )
        return Response(InvoiceReadSerializer(invoice, context={"request": request}).data)

    def destroy(self, request, *args, **kwargs):
        delete_invoice(invoice_id=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Invoice deleted."}, status=status.HTTP_200_OK)


class InvoiceDueDateUpdateView(generics.GenericAPIView):
    """
    PATCH /billing/invoices/<pk>/due-date/   — admin/superuser only.
    Edits a CONFIRMED invoice's due date at any time (e.g. extending an
    overdue invoice). Immediately re-runs the customer's credit score.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = InvoiceDueDateUpdateSerializer

    def patch(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = update_invoice_due_date(
            invoice_id=self.kwargs["pk"],
            new_due_date=serializer.validated_data["payment_due_date"],
            user=request.user,
        )
        return Response(InvoiceReadSerializer(invoice, context={"request": request}).data)


# ---------------------------------------------------------------------------
# Confirm Invoice (admin/superuser only)
# ---------------------------------------------------------------------------

class InvoiceConfirmView(generics.UpdateAPIView):
    """
    POST /billing/invoices/<pk>/confirm/
    Confirms a draft — releases stock, runs FIFO, snapshots prices.
    Admin + superuser only.
    """
    permission_classes = [IsAdminOrSuperuser]
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        invoice = confirm_invoice(invoice_id=self.kwargs["pk"], user=request.user)
        return Response(InvoiceReadSerializer(invoice, context={"request": request}).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

class PaymentListCreateView(generics.ListCreateAPIView):
    """
    GET  /billing/invoices/<invoice_id>/payments/
    POST /billing/invoices/<invoice_id>/payments/
    """
    permission_classes = [IsAdminOrSuperuserOrReadOnly]

    def get_serializer_class(self):
        return PaymentWriteSerializer if self.request.method == "POST" else PaymentReadSerializer

    def get_queryset(self):
        return get_payments_for_invoice(self.kwargs["invoice_id"])

    def list(self, request, *args, **kwargs):
        # Batch-fetch every payment's allocations in ONE query for the
        # current page (not one per payment) — PaymentReadSerializer.
        # get_allocations reads from this context instead of querying
        # live per object. Same fix as the N+1 caught in profits' detail
        # view; PaymentReadSerializer is also used nested/listed elsewhere
        # (InvoicePaymentSummarySerializer, here), so it needed it too.
        from payment_methods.selectors import get_allocations_by_source_ids

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset
        context = self.get_serializer_context()
        context["payment_allocations"] = get_allocations_by_source_ids(
            "billing.payment", [p.id for p in rows],
        )
        serializer = self.get_serializer(rows, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        payment = create_payment(
            invoice_id=self.kwargs["invoice_id"],
            amount=d["amount"],
            method_allocations=_as_splits(d["method_allocations"]),
            payment_date=d["payment_date"],
            note=d.get("note", ""),
            user=request.user,
        )
        return Response(PaymentReadSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDestroyView(generics.RetrieveDestroyAPIView):
    """
    GET    /billing/payments/<pk>/  — single payment, by id (not filtered
           through the /billing/payments/ search list — see
           PaymentDetailPage.jsx, which used to fetch up to 500 rows and
           find() client-side just to open one payment).
    DELETE /billing/payments/<pk>/  — soft-deletes a payment. Admin + superuser only.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class    = PaymentReadSerializer

    def get_object(self):
        return get_payment_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_payment(payment_id=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Payment deleted."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Return
# ---------------------------------------------------------------------------

class ReturnListCreateView(generics.ListCreateAPIView):
    """
    GET  /billing/invoices/<invoice_id>/returns/  — list returns for invoice
    POST /billing/invoices/<invoice_id>/returns/  — create return request (all authenticated)
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        return ReturnCreateSerializer if self.request.method == "POST" else ReturnReadSerializer

    def get_queryset(self):
        return get_returns_for_invoice(self.kwargs["invoice_id"])

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        return_record = create_return(
            invoice_id=self.kwargs["invoice_id"],
            items=d["items"],
            note=d.get("note", ""),
            user=request.user,
        )
        # Same reasoning as InvoiceListCreateView.create — re-fetch through
        # the selector that prefetches shelf_allocations before serializing.
        return_record = get_return_by_id(return_record.id)
        return Response(ReturnReadSerializer(return_record, context={"request": request}).data, status=status.HTTP_201_CREATED)


class ReturnAcceptView(generics.UpdateAPIView):
    """
    POST /billing/returns/<pk>/accept/
    Accepts a pending return — reverses FIFO, restores inventory, credits balance.
    Admin + superuser only.
    """
    permission_classes = [IsAdminOrSuperuser]
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        return_record = accept_return(return_id=self.kwargs["pk"], user=request.user)
        return Response(ReturnReadSerializer(return_record, context={"request": request}).data, status=status.HTTP_200_OK)


class ReturnRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /billing/returns/<pk>/  — retrieve
    PATCH  /billing/returns/<pk>/  — replace items (PENDING only)
    DELETE /billing/returns/<pk>/  — cancel / soft delete (PENDING only)
    Same permission level as creating a return (IsAuthenticated) — editing/
    cancelling your own not-yet-effective return request is no more
    sensitive than creating one; accepting it is the admin-gated action.
    """
    permission_classes = [IsAuthenticated]
    http_method_names  = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return ReturnUpdateSerializer if self.request.method == "PATCH" else ReturnReadSerializer

    def get_object(self):
        return get_return_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        return_record = update_return_items(
            return_id=self.kwargs["pk"],
            items=d["items"],
            note=d.get("note"),
            user=request.user,
        )
        return Response(ReturnReadSerializer(return_record, context={"request": request}).data)

    def destroy(self, request, *args, **kwargs):
        cancel_return(return_id=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Return cancelled."}, status=status.HTTP_200_OK)


class AllReturnsView(generics.ListAPIView):
    """
    GET /billing/returns/
    Search all returns across all invoices.

    Query params:
        reference     : Return reference number (partial match)
        bill_number   : Invoice bill number (partial match)
        customer_name : Customer name (partial match)
        status        : pending | accepted
        date_from     : YYYY-MM-DD
        date_to       : YYYY-MM-DD
    """
    permission_classes = [IsAuthenticated]
    serializer_class   = ReturnReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_returns(
            reference     = p.get("reference"),
            bill_number   = p.get("bill_number"),
            customer_name = p.get("customer_name"),
            status        = p.get("status"),
            date_from     = p.get("date_from"),
            date_to       = p.get("date_to"),
        )


# ---------------------------------------------------------------------------
# Payment summary views
# ---------------------------------------------------------------------------

from .selectors import (
    get_invoice_payment_summary,
    get_customer_outstanding,
    get_customers_with_outstanding,
)
from .serializers import (
    CustomerOutstandingSerializer,
    CustomerWithOutstandingSerializer,
    InvoicePaymentSummarySerializer,
)


class InvoicePaymentSummaryView(generics.RetrieveAPIView):
    """
    GET /billing/invoices/<pk>/payment-summary/
    Returns full payment breakdown for a single invoice:
      - subtotal, cash_received, credit_outstanding, total_paid,
        remaining_amount, payment_status, all payment records.
    Accessible to all authenticated users.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = InvoicePaymentSummarySerializer

    def get_object(self):
        return get_invoice_payment_summary(self.kwargs["pk"])

    def retrieve(self, request, *args, **kwargs):
        # Same batched-allocations fix as PaymentListCreateView.list() —
        # this invoice's nested `payments` list would otherwise N+1 one
        # allocations query per payment.
        from payment_methods.selectors import get_allocations_by_source_ids

        instance = self.get_object()
        context = self.get_serializer_context()
        context["payment_allocations"] = get_allocations_by_source_ids(
            "billing.payment", [p.id for p in instance.payments.all()],
        )
        serializer = self.get_serializer(instance, context=context)
        return Response(serializer.data)


class CustomerOutstandingView(generics.RetrieveAPIView):
    """
    GET /billing/customers/<pk>/outstanding/
    Returns total outstanding balance for a specific customer
    across all their confirmed invoices.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        summary = get_customer_outstanding(customer_id=self.kwargs["pk"])
        serializer = CustomerOutstandingSerializer(summary)
        return Response(serializer.data)


class CustomerOutstandingListView(generics.ListAPIView):
    """
    GET /billing/customers/outstanding/
    Lists all customers who have credit_outstanding > 0.

    Query params:
        search          : customer name or code (partial match)
        payment_status  : unpaid | partial
        min_outstanding : minimum total outstanding
        max_outstanding : maximum total outstanding
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerWithOutstandingSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_customers_with_outstanding(
            search          = p.get("search"),
            customer_name   = p.get("customer_name"),
            customer_code   = p.get("customer_code"),
            payment_status  = p.get("payment_status"),
            min_outstanding = p.get("min_outstanding"),
            max_outstanding = p.get("max_outstanding"),
        )


# ---------------------------------------------------------------------------
# Invoice filtering
# ---------------------------------------------------------------------------

class InvoiceFilteredListView(generics.ListAPIView):
    """
    GET /billing/invoices/search/
    Master invoice list with all filters combined.

    Query params:
        status          : draft | confirmed | returned | partial
        customer_name   : partial match
        customer_code   : partial match
        bill_number     : partial match
        date            : YYYY-MM-DD  (exact day)
        date_from       : YYYY-MM-DD
        date_to         : YYYY-MM-DD
        payment_status  : unpaid | partial | paid
        min_amount      : minimum grand_total
        max_amount      : maximum grand_total
    """
    permission_classes = [IsAuthenticated]
    serializer_class   = InvoiceReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_filtered_invoices(
            status         = p.get("status"),
            customer_name  = p.get("customer_name"),
            customer_code  = p.get("customer_code"),
            bill_number    = p.get("bill_number"),
            date           = p.get("date"),
            date_from      = p.get("date_from"),
            date_to        = p.get("date_to"),
            payment_status = p.get("payment_status"),
            min_amount     = p.get("min_amount"),
            max_amount     = p.get("max_amount"),
        )


class ConfirmedInvoiceListView(generics.ListAPIView):
    """
    GET /billing/invoices/confirmed/
    Dedicated confirmed invoices endpoint with same filter params.
    """
    permission_classes = [IsAuthenticated]
    serializer_class   = InvoiceReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_filtered_invoices(
            status         = Invoice.Status.CONFIRMED,
            customer_name  = p.get("customer_name"),
            customer_code  = p.get("customer_code"),
            bill_number    = p.get("bill_number"),
            date           = p.get("date"),
            date_from      = p.get("date_from"),
            date_to        = p.get("date_to"),
            payment_status = p.get("payment_status"),
            min_amount     = p.get("min_amount"),
            max_amount     = p.get("max_amount"),
        )


# ---------------------------------------------------------------------------
# PDF views
# ---------------------------------------------------------------------------

from django.http import HttpResponse, FileResponse
from rest_framework.views import APIView

from .pdf_service import (
    delete_saved_pdf,
    generate_invoice_pdf_bytes,
    get_saved_pdfs_for_invoice,
    save_invoice_pdf,
)
from .serializers import SavedInvoicePDFSerializer, SavePDFRequestSerializer


class InvoicePrintView(APIView):
    """
    GET /billing/invoices/<pk>/print/?is_draft=true|false

    Streams the PDF directly to the client — nothing saved to disk.
    - is_draft=true  → shows DRAFT watermark (all authenticated users)
    - is_draft=false → clean invoice (admin/superuser only)

    Browser/Postman receives the PDF bytes; print dialog is triggered
    client-side by setting Content-Disposition: inline.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        is_draft_param = request.query_params.get("is_draft", "false").lower() == "true"

        # Normal users can ONLY print draft-watermarked version
        if not is_draft_param and not request.user.is_staff:
            return Response(
                {"detail": "Normal users can only print the draft version."},
                status=status.HTTP_403_FORBIDDEN,
            )

        pdf_bytes, filename = generate_invoice_pdf_bytes(
            invoice_id=pk,
            is_draft=is_draft_param,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        # inline = browser shows it / triggers print dialog; not a download
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class InvoiceSavePDFView(generics.CreateAPIView):
    """
    POST /billing/invoices/<pk>/pdf/save/
    Saves the PDF to disk and creates a SavedInvoicePDF record.
    Admin + superuser only.

    Body:
        file_name : string (optional, defaults to bill number)
        is_draft  : bool   (default false)

    Returns the SavedInvoicePDF record with file_url.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SavePDFRequestSerializer

    def create(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        # Default file name = bill number
        from .selectors import get_invoice_by_id as _get
        invoice   = _get(pk)
        file_name = d.get("file_name") or invoice.bill_number

        saved = save_invoice_pdf(
            invoice_id=pk,
            file_name=file_name,
            is_draft=False,   # save always produces clean confirmed PDF
            user=request.user,
        )
        return Response(
            SavedInvoicePDFSerializer(saved, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class InvoiceSavedPDFListView(generics.ListAPIView):
    """
    GET /billing/invoices/<pk>/pdf/
    Lists all saved PDFs for an invoice. Admin + superuser only.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SavedInvoicePDFSerializer

    def get_queryset(self):
        return get_saved_pdfs_for_invoice(self.kwargs["pk"])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx


class SavedPDFDeleteView(generics.DestroyAPIView):
    """
    DELETE /billing/pdf/<saved_pdf_id>/
    Soft-deletes the record and removes the file from disk.
    Admin + superuser only.
    """
    permission_classes = [IsAdminOrSuperuser]

    def destroy(self, request, saved_pdf_id):
        delete_saved_pdf(saved_pdf_id=saved_pdf_id, user=request.user)
        return Response({"detail": "PDF deleted."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# All outstanding invoices
# ---------------------------------------------------------------------------

from .selectors import get_all_outstanding_invoices


class AllOutstandingInvoicesView(generics.ListAPIView):
    """
    GET /billing/invoices/outstanding/
    All invoices with credit_outstanding > 0, across ALL customers.

    Query params:
        customer_name   : partial match on customer name
        customer_code   : partial match on customer code
        payment_status  : unpaid | partial
        date_from       : YYYY-MM-DD
        date_to         : YYYY-MM-DD
        min_outstanding : minimum credit_outstanding
        max_outstanding : maximum credit_outstanding

    Results sorted by highest outstanding first.
    """
    permission_classes = [IsAuthenticated]
    serializer_class   = InvoiceReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_outstanding_invoices(
            customer_name   = p.get("customer_name"),
            customer_code   = p.get("customer_code"),
            payment_status  = p.get("payment_status"),
            date_from       = p.get("date_from"),
            date_to         = p.get("date_to"),
            min_outstanding = p.get("min_outstanding"),
            max_outstanding = p.get("max_outstanding"),
        )


# ---------------------------------------------------------------------------
# Global billing payment search
# ---------------------------------------------------------------------------

from .selectors import get_all_invoice_payments


class AllInvoicePaymentsView(AllocationsListMixin, generics.ListAPIView):
    """
    GET /billing/payments/
    Search all billing payments across all invoices.

    Query params:
        reference     : PAY reference number (partial match)
        customer_name : partial match
        customer_code : partial match
        method        : cash | jazzcash | easypaisa | bank
        date_from     : YYYY-MM-DD
        date_to       : YYYY-MM-DD
    """
    permission_classes = [IsAuthenticated]
    serializer_class   = PaymentReadSerializer
    allocations_source_model = "billing.payment"
    allocations_context_key  = "payment_allocations"

    def get_queryset(self):
        p = self.request.query_params
        return get_all_invoice_payments(
            reference     = p.get("reference"),
            customer_name = p.get("customer_name"),
            customer_code = p.get("customer_code"),
            method        = p.get("method"),
            date_from     = p.get("date_from"),
            date_to       = p.get("date_to"),
        )


# ---------------------------------------------------------------------------
# Shelf allocations — sale line consumption / return line put-away
# ---------------------------------------------------------------------------

class InvoiceCandidateShelvesView(generics.ListAPIView):
    """
    GET /billing/shelves/candidates/?product_id=<id>
    Shelves currently holding stock of the given product — the dropdown
    source for picking which shelf(s) a draft sale line is fulfilled from.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CandidateShelfSerializer

    def get_queryset(self):
        from purchases.selectors import get_candidate_shelves_for_product

        product_id = self.request.query_params.get("product_id")
        if not product_id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"product_id": "This query parameter is required."})
        return get_candidate_shelves_for_product(
            int(product_id), search=self.request.query_params.get("search"),
        )


class InvoiceAutoAllocateShelvesView(APIView):
    """
    POST /billing/shelves/auto-allocate/
    Thin pass-through to purchases.selectors.compute_auto_shelf_allocation —
    same shared implementation as the purchases app's own
    /purchases/shelves/auto-allocate/, just namespaced under /billing/ so
    the invoice-items frontend never has to reach into another app's URLs
    (mirrors InvoiceCandidateShelvesView above).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from purchases.selectors import compute_auto_shelf_allocation

        req = AutoAllocateShelvesRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        result = compute_auto_shelf_allocation(**req.validated_data)
        return Response(AutoAllocateShelvesResponseSerializer(result).data)


class SetInvoiceItemShelfAllocationsView(APIView):
    """
    POST /billing/invoice-items/<pk>/shelf-allocations/
    Replaces the shelf consumption allocations for one draft invoice line.
    Only allowed while the invoice is DRAFT (enforced in the service layer).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        serializer = SetShelfAllocationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        set_invoice_item_shelf_allocations(
            invoice_item_id=pk,
            allocations=[
                {"shelf_id": a["shelf_id"], "quantity": a["quantity"]}
                for a in d["allocations"]
            ],
            user=request.user,
        )
        invoice_item = get_invoice_item_with_allocations_by_id(pk)
        return Response(InvoiceItemReadSerializer(invoice_item, context={"request": request}).data, status=status.HTTP_200_OK)


class SetReturnItemShelfAllocationsView(APIView):
    """
    POST /billing/return-items/<pk>/shelf-allocations/
    Replaces the shelf put-away allocations for one pending return line.
    Only allowed while the return is PENDING (enforced in the service layer).
    Any shelf is valid (put-away, no availability check).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        serializer = SetShelfAllocationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        set_return_item_shelf_allocations(
            return_item_id=pk,
            allocations=[
                {"shelf_id": a["shelf_id"], "quantity": a["quantity"]}
                for a in d["allocations"]
            ],
            user=request.user,
        )
        return_item = get_return_item_by_id(pk)
        return Response(ReturnItemReadSerializer(return_item, context={"request": request}).data, status=status.HTTP_200_OK)