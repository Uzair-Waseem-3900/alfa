from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsAdminOrSuperuser
from .selectors import (
    get_all_customer_ledgers,
    get_all_ledgers,
    get_customer_ledger_by_customer_id,
    get_customer_ledger_by_id,
    get_customer_ledger_entries,
    get_ledger_by_id,
    get_ledger_by_supplier_id,
    get_ledger_entries,
    get_saved_pdfs_for_customer_ledger,
    get_saved_pdfs_for_ledger,
)
from .serializers import (
    CustomerLedgerReadSerializer,
    LedgerEntrySerializer,
    LedgerResponseSerializer,
    SavedCustomerLedgerPDFSerializer,
    SavedLedgerPDFSerializer,
    SaveLedgerPDFRequestSerializer,
    SupplierLedgerReadSerializer,
)
from .services import (
    delete_customer_ledger,
    delete_customer_ledger_pdf,
    delete_ledger,
    delete_ledger_pdf,
    generate_customer_ledger_pdf_bytes,
    generate_ledger_pdf_bytes,
    save_customer_ledger_pdf,
    save_ledger_pdf,
)


def _paginate_entries(entries: list, request) -> dict:
    """
    Manual page-number pagination for an already-materialized list.
    entries has its running balance computed cumulatively over the FULL
    history, so it must stay a plain Python list — this only slices it for
    display. Same response shape as StandardResultsSetPagination.
    """
    try:
        page_size = min(int(request.query_params.get("page_size", 25)), 500)
    except (TypeError, ValueError):
        page_size = 25
    try:
        page = max(int(request.query_params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1

    count = len(entries)
    total_pages = max(-(-count // page_size), 1)  # ceil division
    start = (page - 1) * page_size

    return {
        "count": count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "results": entries[start:start + page_size],
    }


class SupplierLedgerListView(generics.ListAPIView):
    """
    GET /ledger/
    List all supplier ledgers.
    Filter: ?search= (supplier name or code)
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SupplierLedgerReadSerializer

    def get_queryset(self):
        return get_all_ledgers(search=self.request.query_params.get("search"))


class SupplierLedgerDetailView(APIView):
    """
    GET /ledger/<pk>/
    Returns ledger entries with running balance for a supplier.

    Query params:
        date_from   : YYYY-MM-DD
        date_to     : YYYY-MM-DD
        entry_type  : purchase | payment | return | advance
        reference   : partial match on reference number
        min_amount  : min debit or credit amount
        max_amount  : max debit or credit amount
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, pk):
        p         = request.query_params
        ledger    = get_ledger_by_id(pk)
        entries, closing_balance = get_ledger_entries(
            ledger     = ledger,
            date_from  = p.get("date_from"),
            date_to    = p.get("date_to"),
            entry_type = p.get("entry_type"),
            reference  = p.get("reference"),
            min_amount = p.get("min_amount"),
            max_amount = p.get("max_amount"),
        )
        paginated = _paginate_entries(entries, request)
        data = {
            "ledger"          : SupplierLedgerReadSerializer(ledger).data,
            "closing_balance" : closing_balance,
            "date_from"       : p.get("date_from"),
            "date_to"         : p.get("date_to"),
            **paginated,
            "results"         : LedgerEntrySerializer(paginated["results"], many=True).data,
        }
        return Response(data)

    def delete(self, request, pk):
        """
        DELETE /ledger/<pk>/
        Soft-deletes the ledger. Only allowed once the linked supplier is
        itself already deleted.
        """
        delete_ledger(pk=pk, user=request.user)
        return Response({"detail": "Ledger deleted."}, status=status.HTTP_200_OK)


class SupplierLedgerBySupplierView(APIView):
    """
    GET /ledger/supplier/<supplier_id>/
    Returns ledger by supplier id (convenience endpoint).
    Supports same query params as SupplierLedgerDetailView.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, supplier_id):
        p      = request.query_params
        ledger = get_ledger_by_supplier_id(supplier_id)
        entries, closing_balance = get_ledger_entries(
            ledger     = ledger,
            date_from  = p.get("date_from"),
            date_to    = p.get("date_to"),
            entry_type = p.get("entry_type"),
            reference  = p.get("reference"),
            min_amount = p.get("min_amount"),
            max_amount = p.get("max_amount"),
        )
        paginated = _paginate_entries(entries, request)
        data = {
            "ledger"          : SupplierLedgerReadSerializer(ledger).data,
            "closing_balance" : closing_balance,
            "date_from"       : p.get("date_from"),
            "date_to"         : p.get("date_to"),
            **paginated,
            "results"         : LedgerEntrySerializer(paginated["results"], many=True).data,
        }
        return Response(data)


class LedgerPrintView(APIView):
    """
    GET /ledger/<pk>/print/
    Streams PDF — nothing saved.
    Optional: ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, pk):
        date_from = request.query_params.get("date_from") or None
        date_to   = request.query_params.get("date_to") or None
        pdf_bytes, filename = generate_ledger_pdf_bytes(
            ledger_id=pk, date_from=date_from, date_to=date_to,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class LedgerSavePDFView(generics.CreateAPIView):
    """
    POST /ledger/<pk>/pdf/save/
    Saves PDF to disk and creates SavedLedgerPDF record.

    Body:
        file_name : string (optional)
        date_from : YYYY-MM-DD (optional)
        date_to   : YYYY-MM-DD (optional)
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SaveLedgerPDFRequestSerializer

    def create(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d         = serializer.validated_data
        ledger    = get_ledger_by_id(pk)
        file_name = d.get("file_name") or f"Ledger_{ledger.supplier_code}"

        saved = save_ledger_pdf(
            ledger_id = pk,
            file_name = file_name,
            date_from = d.get("date_from"),
            date_to   = d.get("date_to"),
            user      = request.user,
        )
        return Response(
            SavedLedgerPDFSerializer(saved, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class LedgerSavedPDFListView(generics.ListAPIView):
    """GET /ledger/<pk>/pdf/ — list saved PDFs for a ledger."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SavedLedgerPDFSerializer

    def get_queryset(self):
        return get_saved_pdfs_for_ledger(self.kwargs["pk"])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx


class LedgerSavedPDFDeleteView(generics.DestroyAPIView):
    """DELETE /ledger/pdf/<saved_pdf_id>/"""
    permission_classes = [IsAdminOrSuperuser]

    def destroy(self, request, saved_pdf_id):
        delete_ledger_pdf(saved_pdf_id=saved_pdf_id, user=request.user)
        return Response({"detail": "Ledger PDF deleted."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Customer ledger views — mirror the supplier views above.
# ---------------------------------------------------------------------------

class CustomerLedgerListView(generics.ListAPIView):
    """
    GET /ledger/customers/
    List all customer ledgers.
    Filter: ?search= (customer name or code)
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = CustomerLedgerReadSerializer

    def get_queryset(self):
        return get_all_customer_ledgers(search=self.request.query_params.get("search"))


class CustomerLedgerDetailView(APIView):
    """
    GET /ledger/customers/<pk>/
    Returns ledger entries with running balance for a customer.

    Query params:
        date_from   : YYYY-MM-DD
        date_to     : YYYY-MM-DD
        entry_type  : sale | payment | return | advance | opening_balance
        reference   : partial match on reference number
        min_amount  : min debit or credit amount
        max_amount  : max debit or credit amount
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, pk):
        p         = request.query_params
        ledger    = get_customer_ledger_by_id(pk)
        entries, closing_balance = get_customer_ledger_entries(
            ledger     = ledger,
            date_from  = p.get("date_from"),
            date_to    = p.get("date_to"),
            entry_type = p.get("entry_type"),
            reference  = p.get("reference"),
            min_amount = p.get("min_amount"),
            max_amount = p.get("max_amount"),
        )
        paginated = _paginate_entries(entries, request)
        data = {
            "ledger"          : CustomerLedgerReadSerializer(ledger).data,
            "closing_balance" : closing_balance,
            "date_from"       : p.get("date_from"),
            "date_to"         : p.get("date_to"),
            **paginated,
            "results"         : LedgerEntrySerializer(paginated["results"], many=True).data,
        }
        return Response(data)

    def delete(self, request, pk):
        """
        DELETE /ledger/customers/<pk>/
        Soft-deletes the ledger. Only allowed once the linked customer is
        itself already deleted.
        """
        delete_customer_ledger(pk=pk, user=request.user)
        return Response({"detail": "Ledger deleted."}, status=status.HTTP_200_OK)


class CustomerLedgerByCustomerView(APIView):
    """
    GET /ledger/customers/by-customer/<customer_id>/
    Returns ledger by customer id (convenience endpoint).
    Supports same query params as CustomerLedgerDetailView.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, customer_id):
        p      = request.query_params
        ledger = get_customer_ledger_by_customer_id(customer_id)
        entries, closing_balance = get_customer_ledger_entries(
            ledger     = ledger,
            date_from  = p.get("date_from"),
            date_to    = p.get("date_to"),
            entry_type = p.get("entry_type"),
            reference  = p.get("reference"),
            min_amount = p.get("min_amount"),
            max_amount = p.get("max_amount"),
        )
        paginated = _paginate_entries(entries, request)
        data = {
            "ledger"          : CustomerLedgerReadSerializer(ledger).data,
            "closing_balance" : closing_balance,
            "date_from"       : p.get("date_from"),
            "date_to"         : p.get("date_to"),
            **paginated,
            "results"         : LedgerEntrySerializer(paginated["results"], many=True).data,
        }
        return Response(data)


class CustomerLedgerPrintView(APIView):
    """
    GET /ledger/customers/<pk>/print/
    Streams PDF — nothing saved.
    Optional: ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, pk):
        date_from = request.query_params.get("date_from") or None
        date_to   = request.query_params.get("date_to") or None
        pdf_bytes, filename = generate_customer_ledger_pdf_bytes(
            ledger_id=pk, date_from=date_from, date_to=date_to,
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class CustomerLedgerSavePDFView(generics.CreateAPIView):
    """
    POST /ledger/customers/<pk>/pdf/save/
    Saves PDF to disk and creates SavedCustomerLedgerPDF record.

    Body:
        file_name : string (optional)
        date_from : YYYY-MM-DD (optional)
        date_to   : YYYY-MM-DD (optional)
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SaveLedgerPDFRequestSerializer

    def create(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d         = serializer.validated_data
        ledger    = get_customer_ledger_by_id(pk)
        file_name = d.get("file_name") or f"Ledger_{ledger.customer_code}"

        saved = save_customer_ledger_pdf(
            ledger_id = pk,
            file_name = file_name,
            date_from = d.get("date_from"),
            date_to   = d.get("date_to"),
            user      = request.user,
        )
        return Response(
            SavedCustomerLedgerPDFSerializer(saved, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class CustomerLedgerSavedPDFListView(generics.ListAPIView):
    """GET /ledger/customers/<pk>/pdf/ — list saved PDFs for a customer ledger."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SavedCustomerLedgerPDFSerializer

    def get_queryset(self):
        return get_saved_pdfs_for_customer_ledger(self.kwargs["pk"])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx


class CustomerLedgerSavedPDFDeleteView(generics.DestroyAPIView):
    """DELETE /ledger/customers/pdf/<saved_pdf_id>/"""
    permission_classes = [IsAdminOrSuperuser]

    def destroy(self, request, saved_pdf_id):
        delete_customer_ledger_pdf(saved_pdf_id=saved_pdf_id, user=request.user)
        return Response({"detail": "Ledger PDF deleted."}, status=status.HTTP_200_OK)