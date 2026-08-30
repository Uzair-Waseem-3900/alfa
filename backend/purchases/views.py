from decimal import Decimal
from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from payment_methods.mixins import AllocationsListMixin

from .models import PurchaseOrder
from .pdf_service import (
    delete_purchase_order_pdf, generate_purchase_order_pdf_bytes,
    get_saved_pdfs_for_order, save_purchase_order_pdf,
)
from .permissions import IsAdminOrSuperuser, IsAdminOrSuperuserOrReadOnly
from .selectors import (
    compute_auto_shelf_allocation,
    get_all_categories, get_all_inventory, get_all_lost_inventory_records,
    get_all_products, get_all_purchase_orders, get_all_returns,
    get_all_shelves, get_all_suppliers, get_candidate_shelves_for_product,
    get_category_by_id,
    get_confirmed_purchase_orders, get_draft_purchase_orders,
    get_fifo_cost_preview, get_inventory_by_product_id, get_inventory_stats,
    get_lost_inventory_item_by_id, get_lost_inventory_record_by_id,
    get_low_stock_inventory, get_order_payment_summary,
    get_out_of_stock_inventory,
    get_payments_for_order, get_purchase_item_with_allocations_by_id,
    get_purchase_order_by_id, get_purchase_return_by_id,
    get_purchase_return_item_with_allocations_by_id,
    get_returns_for_order, get_shelf_by_id, get_shelf_stock_rows,
    get_supplier_by_id, get_supplier_payable_summary,
    get_supplier_payment_by_id, get_suppliers_with_outstanding,
)
from .serializers import (
    AutoAllocateShelvesRequestSerializer, AutoAllocateShelvesResponseSerializer,
    CandidateShelfSerializer,
    CategoryReadSerializer, CategoryWriteSerializer,
    InventoryReadSerializer, InventoryStatsSerializer,
    LostInventoryCreateSerializer,
    LostInventoryFifoPreviewQuerySerializer,
    LostInventoryFifoPreviewSerializer, LostInventoryItemReadSerializer,
    LostInventoryReadSerializer, MarkLostInventoryFoundSerializer,
    MoveStockSerializer,
    ProductReadSerializer, ProductWriteSerializer,
    PurchaseItemReadSerializer, PurchaseOrderCreateSerializer,
    PurchaseOrderPaymentSummarySerializer, PurchaseOrderReadSerializer,
    PurchaseOrderUpdateSerializer, PurchaseReturnCreateSerializer,
    PurchaseReturnItemReadSerializer,
    PurchaseReturnReadSerializer, PurchaseReturnUpdateSerializer,
    SavedPurchaseOrderPDFSerializer,
    SavePurchaseOrderPDFRequestSerializer, SetShelfAllocationsSerializer,
    ShelfReadSerializer, ShelfStockReadSerializer,
    ShelfWriteSerializer, SupplierPayableSummarySerializer,
    SupplierPaymentReadSerializer, SupplierPaymentWriteSerializer,
    SupplierReadSerializer, SupplierWithOutstandingSerializer,
    SupplierWriteSerializer,
)
from .services import (
    accept_purchase_return, cancel_purchase_return, confirm_purchase_order,
    create_category, create_lost_inventory_record, create_product,
    create_purchase_order, create_purchase_return, create_shelf,
    create_supplier, create_supplier_payment, delete_category,
    delete_product, delete_purchase_order, delete_shelf, delete_supplier,
    delete_supplier_payment, mark_lost_inventory_found, move_shelf_stock,
    set_purchase_item_shelf_allocations,
    set_purchase_return_item_shelf_allocations, update_category,
    update_product, update_purchase_order_items,
    update_purchase_return_items, update_shelf, update_supplier,
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
# Shared mixin
# ---------------------------------------------------------------------------

class ReadWriteSerializerMixin:
    read_serializer_class  = None
    write_serializer_class = None

    def get_serializer_class(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return self.read_serializer_class
        return self.write_serializer_class


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

class CategoryListCreateView(ReadWriteSerializerMixin, generics.ListCreateAPIView):
    permission_classes     = [IsAdminOrSuperuser]
    read_serializer_class  = CategoryReadSerializer
    write_serializer_class = CategoryWriteSerializer

    def get_queryset(self):
        return get_all_categories()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = create_category(**serializer.validated_data, user=request.user)
        return Response(CategoryReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class CategoryRetrieveUpdateDestroyView(ReadWriteSerializerMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes     = [IsAdminOrSuperuser]
    read_serializer_class  = CategoryReadSerializer
    write_serializer_class = CategoryWriteSerializer
    http_method_names      = ["get", "patch", "delete"]

    def get_object(self):
        return get_category_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = update_category(pk=self.kwargs["pk"], user=request.user, **serializer.validated_data)
        return Response(CategoryReadSerializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        delete_category(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Category deleted."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Shelf
# ---------------------------------------------------------------------------

class ShelfListCreateView(ReadWriteSerializerMixin, generics.ListCreateAPIView):
    permission_classes     = [IsAdminOrSuperuser]
    read_serializer_class  = ShelfReadSerializer
    write_serializer_class = ShelfWriteSerializer

    def get_queryset(self):
        return get_all_shelves(
            search=self.request.query_params.get("search"),
            product_search=self.request.query_params.get("product_search"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = create_shelf(**serializer.validated_data, user=request.user)
        return Response(ShelfReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class ShelfRetrieveUpdateDestroyView(ReadWriteSerializerMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes     = [IsAdminOrSuperuser]
    read_serializer_class  = ShelfReadSerializer
    write_serializer_class = ShelfWriteSerializer
    http_method_names      = ["get", "patch", "delete"]

    def get_object(self):
        return get_shelf_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = update_shelf(pk=self.kwargs["pk"], user=request.user, **serializer.validated_data)
        return Response(ShelfReadSerializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        delete_shelf(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Shelf deleted."}, status=status.HTTP_200_OK)


class ShelfStockListView(generics.ListAPIView):
    """GET /purchases/shelves/<pk>/stock/ — products + quantities on one shelf."""
    permission_classes = [IsAdminOrSuperuserOrReadOnly]
    serializer_class   = ShelfStockReadSerializer

    def get_queryset(self):
        get_shelf_by_id(self.kwargs["pk"])  # 404s if the shelf doesn't exist
        return get_shelf_stock_rows(self.kwargs["pk"], search=self.request.query_params.get("search"))


class CandidateShelvesForProductView(generics.ListAPIView):
    """
    GET /purchases/shelves/candidates/?product_id=<id>
    Shelves currently holding stock of a product — the dropdown source for
    any consumption allocation context (sale, purchase return, lost
    inventory). Open to all authenticated users, not just admins.
    """
    permission_classes = [IsAuthenticated]
    serializer_class   = CandidateShelfSerializer

    def get_queryset(self):
        from rest_framework.exceptions import ValidationError
        product_id = self.request.query_params.get("product_id")
        if not product_id:
            raise ValidationError({"product_id": "This query parameter is required."})
        return get_candidate_shelves_for_product(
            int(product_id), search=self.request.query_params.get("search"),
        )


class AutoAllocateShelvesView(APIView):
    """
    POST /purchases/shelves/auto-allocate/
    Body: {product_id, quantity, exclude_shelf_ids: [...]}

    Greedily fills `quantity` of product_id across shelves currently
    holding stock (largest available quantity first), skipping any shelf id
    already in exclude_shelf_ids — so calling this after the user has
    manually picked one or two shelves only fills the remaining gap and
    never touches their existing rows. Shared by every consumption
    allocation context (invoice items, purchase returns to supplier, lost
    inventory) through compute_auto_shelf_allocation — one implementation.
    Open to all authenticated users, matching CandidateShelvesForProductView.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        req = AutoAllocateShelvesRequestSerializer(data=request.data)
        req.is_valid(raise_exception=True)
        result = compute_auto_shelf_allocation(**req.validated_data)
        return Response(AutoAllocateShelvesResponseSerializer(result).data)


class MoveStockView(APIView):
    """POST /purchases/shelves/move/ — move a product's stock between two shelves."""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request):
        serializer = MoveStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        move_shelf_stock(
            from_shelf_id=d["from_shelf_id"], to_shelf_id=d["to_shelf_id"],
            product_id=d["product_id"], quantity=d["quantity"], user=request.user,
        )
        return Response({"detail": "Stock moved."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Supplier
# ---------------------------------------------------------------------------

class SupplierListCreateView(ReadWriteSerializerMixin, generics.ListCreateAPIView):
    # Excluded from pagination — client confirmed suppliers are a small,
    # bounded list (~10-15 rows), so paginating it is pure overhead.
    pagination_class       = None
    permission_classes     = [IsAdminOrSuperuser]
    read_serializer_class  = SupplierReadSerializer
    write_serializer_class = SupplierWriteSerializer

    def get_queryset(self):
        return get_all_suppliers(search=self.request.query_params.get("search"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = create_supplier(**serializer.validated_data, user=request.user)
        return Response(SupplierReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class SupplierRetrieveUpdateDestroyView(ReadWriteSerializerMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes     = [IsAdminOrSuperuser]
    read_serializer_class  = SupplierReadSerializer
    write_serializer_class = SupplierWriteSerializer
    http_method_names      = ["get", "patch", "delete"]

    def get_object(self):
        return get_supplier_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = update_supplier(pk=self.kwargs["pk"], user=request.user, **serializer.validated_data)
        return Response(SupplierReadSerializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        delete_supplier(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Supplier deleted."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class ProductListCreateView(ReadWriteSerializerMixin, generics.ListCreateAPIView):
    permission_classes     = [IsAdminOrSuperuser]
    read_serializer_class  = ProductReadSerializer
    write_serializer_class = ProductWriteSerializer

    def get_queryset(self):
        return get_all_products(search=self.request.query_params.get("search"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d   = serializer.validated_data
        obj = create_product(
            name=d["name"], code=d["code"],
            category_id=d["category"].pk,
            user=request.user,
        )
        return Response(ProductReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class ProductRetrieveUpdateDestroyView(ReadWriteSerializerMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes     = [IsAdminOrSuperuser]
    read_serializer_class  = ProductReadSerializer
    write_serializer_class = ProductWriteSerializer
    http_method_names      = ["get", "patch", "delete"]

    def get_object(self):
        from .selectors import get_product_by_id
        return get_product_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        d   = serializer.validated_data
        obj = update_product(
            pk=self.kwargs["pk"],
            name=d.get("name"), code=d.get("code"),
            category_id=d["category"].pk if "category" in d else None,
            user=request.user,
        )
        return Response(ProductReadSerializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        delete_product(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Product deleted."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# PurchaseOrder — list/create/search/filter
# ---------------------------------------------------------------------------

class PurchaseOrderListCreateView(generics.ListCreateAPIView):
    """
    GET  /purchases/orders/         — all orders with full filter support
    POST /purchases/orders/         — create draft order

    Filter params:
        status, supplier_name, supplier_code, order_number,
        date, date_from, date_to, payment_status, min_amount, max_amount
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return PurchaseOrderCreateSerializer if self.request.method == "POST" else PurchaseOrderReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_purchase_orders(
            status         = p.get("status"),
            supplier_name  = p.get("supplier_name"),
            supplier_code  = p.get("supplier_code"),
            order_number   = p.get("order_number"),
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
        d   = serializer.validated_data
        obj = create_purchase_order(
            supplier_id=d["supplier_id"],
            items=d["items"],
            description=d.get("description", ""),
            payment_type=d.get("payment_type", "after_delivery"),
            advance_amount=d.get("advance_amount", Decimal("0")),
            method_allocations=_as_splits(d.get("method_allocations")),
            user=request.user,
        )
        return Response(PurchaseOrderReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class DraftPurchaseOrderListView(generics.ListAPIView):
    """GET /purchases/orders/drafts/ — all draft orders"""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = PurchaseOrderReadSerializer

    def get_queryset(self):
        return get_draft_purchase_orders()


class ConfirmedPurchaseOrderListView(generics.ListAPIView):
    """
    GET /purchases/orders/confirmed/ — confirmed orders with filters
    Filter params: supplier_name, supplier_code, date_from, date_to, payment_status, min_amount, max_amount
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = PurchaseOrderReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_confirmed_purchase_orders(
            supplier_name  = p.get("supplier_name"),
            supplier_code  = p.get("supplier_code"),
            date_from      = p.get("date_from"),
            date_to        = p.get("date_to"),
            payment_status = p.get("payment_status"),
            min_amount     = p.get("min_amount"),
            max_amount     = p.get("max_amount"),
        )


class PurchaseOrderRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /purchases/orders/<pk>/  — retrieve
    PATCH  /purchases/orders/<pk>/  — update items (DRAFT only)
    DELETE /purchases/orders/<pk>/  — soft delete (DRAFT only)
    """
    permission_classes = [IsAdminOrSuperuser]
    http_method_names  = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return PurchaseOrderUpdateSerializer if self.request.method == "PATCH" else PurchaseOrderReadSerializer

    def get_object(self):
        return get_purchase_order_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d   = serializer.validated_data
        obj = update_purchase_order_items(
            order_id=self.kwargs["pk"],
            items=d["items"],
            description=d.get("description"),
            payment_type=d.get("payment_type"),
            advance_amount=d.get("advance_amount"),
            method_allocations=_as_splits(d.get("method_allocations")),
            user=request.user,
        )
        return Response(PurchaseOrderReadSerializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        delete_purchase_order(order_id=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Purchase order deleted."}, status=status.HTTP_200_OK)


class PurchaseOrderConfirmView(APIView):
    """POST /purchases/orders/<pk>/confirm/ — admin/superuser only"""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, pk):
        obj = confirm_purchase_order(order_id=pk, user=request.user)
        return Response(PurchaseOrderReadSerializer(obj).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Supplier Payment
# ---------------------------------------------------------------------------

class SupplierPaymentListCreateView(generics.ListCreateAPIView):
    """
    GET  /purchases/orders/<order_id>/payments/
    POST /purchases/orders/<order_id>/payments/
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return SupplierPaymentWriteSerializer if self.request.method == "POST" else SupplierPaymentReadSerializer

    def get_queryset(self):
        return get_payments_for_order(self.kwargs["order_id"])

    def list(self, request, *args, **kwargs):
        # Batch-fetch every payment's allocations in ONE query for the
        # current page — same fix as billing.PaymentListCreateView.list().
        from payment_methods.selectors import get_allocations_by_source_ids

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset
        context = self.get_serializer_context()
        context["supplier_payment_allocations"] = get_allocations_by_source_ids(
            "purchases.supplierpayment", [p.id for p in rows],
        )
        serializer = self.get_serializer(rows, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d   = serializer.validated_data
        obj = create_supplier_payment(
            order_id           = self.kwargs["order_id"],
            amount             = d["amount"],
            method_allocations = _as_splits(d["method_allocations"]),
            payment_date       = d["payment_date"],
            note               = d.get("note", ""),
            user               = request.user,
        )
        return Response(SupplierPaymentReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class SupplierPaymentDestroyView(generics.DestroyAPIView):
    """DELETE /purchases/payments/<pk>/"""
    permission_classes = [IsAdminOrSuperuser]

    def get_object(self):
        return get_supplier_payment_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_supplier_payment(payment_id=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Payment deleted."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Supplier Payable Summary
# ---------------------------------------------------------------------------

class PurchaseOrderPaymentSummaryView(generics.RetrieveAPIView):
    """GET /purchases/orders/<pk>/payment-summary/"""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = PurchaseOrderPaymentSummarySerializer

    def get_object(self):
        return get_order_payment_summary(self.kwargs["pk"])

    def retrieve(self, request, *args, **kwargs):
        # Same batched-allocations fix as billing.InvoicePaymentSummaryView
        # — this order's nested `payments` list would otherwise N+1 one
        # allocations query per payment.
        from payment_methods.selectors import get_allocations_by_source_ids

        instance = self.get_object()
        context = self.get_serializer_context()
        context["supplier_payment_allocations"] = get_allocations_by_source_ids(
            "purchases.supplierpayment", [p.id for p in instance.payments.all()],
        )
        serializer = self.get_serializer(instance, context=context)
        return Response(serializer.data)


class SupplierPayableSummaryView(generics.RetrieveAPIView):
    """GET /purchases/suppliers/<pk>/payable-summary/"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, pk):
        summary = get_supplier_payable_summary(supplier_id=pk)
        return Response(SupplierPayableSummarySerializer(summary).data)


class SupplierOutstandingListView(generics.ListAPIView):
    """
    GET /purchases/suppliers/outstanding/
    Lists all suppliers who have outstanding payable > 0, with their total outstanding annotated.

    Query params:
        search          : supplier name or code (partial, case-insensitive)
        payment_status  : unpaid | partial  (filters which orders are counted)
        min_outstanding : minimum total outstanding amount
        max_outstanding : maximum total outstanding amount

    Results sorted by outstanding descending (highest debt first).

    Examples:
        /api/suppliers/outstanding/                         -> all suppliers with any debt
        /api/suppliers/outstanding/?payment_status=unpaid   -> suppliers with fully unpaid orders
        /api/suppliers/outstanding/?payment_status=partial  -> suppliers with partial payments
        /api/suppliers/outstanding/?search=ali              -> search by name/code
        /api/suppliers/outstanding/?min_outstanding=10000   -> owing more than 10,000
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SupplierWithOutstandingSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_suppliers_with_outstanding(
            search          = p.get("search"),
            payment_status  = p.get("payment_status"),
            min_outstanding = p.get("min_outstanding"),
            max_outstanding = p.get("max_outstanding"),
        )


# ---------------------------------------------------------------------------
# Purchase Return
# ---------------------------------------------------------------------------

class PurchaseReturnListCreateView(generics.ListCreateAPIView):
    """
    GET  /purchases/orders/<order_id>/returns/
    POST /purchases/orders/<order_id>/returns/

    Filter params for GET (all returns): status, supplier_name, supplier_code, order_number, date_from, date_to
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return PurchaseReturnCreateSerializer if self.request.method == "POST" else PurchaseReturnReadSerializer

    def get_queryset(self):
        return get_returns_for_order(self.kwargs["order_id"])

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d   = serializer.validated_data
        obj = create_purchase_return(
            order_id=self.kwargs["order_id"],
            items=d["items"],
            note=d.get("note", ""),
            user=request.user,
        )
        return Response(PurchaseReturnReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class AllPurchaseReturnsListView(generics.ListAPIView):
    """
    GET /purchases/returns/
    Master returns list with full filters:
        status, supplier_name, supplier_code, order_number, date_from, date_to
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = PurchaseReturnReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_returns(
            status        = p.get("status"),
            supplier_name = p.get("supplier_name"),
            supplier_code = p.get("supplier_code"),
            order_number  = p.get("order_number"),
            date_from     = p.get("date_from"),
            date_to       = p.get("date_to"),
        )


class PurchaseReturnAcceptView(APIView):
    """POST /purchases/returns/<pk>/accept/ — admin/superuser only"""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, pk):
        obj = accept_purchase_return(return_id=pk, user=request.user)
        return Response(PurchaseReturnReadSerializer(obj).data, status=status.HTTP_200_OK)


class PurchaseReturnRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /purchases/returns/<pk>/  — retrieve
    PATCH  /purchases/returns/<pk>/  — replace items (PENDING only)
    DELETE /purchases/returns/<pk>/  — cancel / soft delete (PENDING only)
    """
    permission_classes = [IsAdminOrSuperuser]
    http_method_names  = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return PurchaseReturnUpdateSerializer if self.request.method == "PATCH" else PurchaseReturnReadSerializer

    def get_object(self):
        return get_purchase_return_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d   = serializer.validated_data
        obj = update_purchase_return_items(
            return_id=self.kwargs["pk"],
            items=d["items"],
            note=d.get("note"),
            user=request.user,
        )
        return Response(PurchaseReturnReadSerializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        cancel_purchase_return(return_id=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Return cancelled."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

class PurchaseOrderPrintView(APIView):
    """
    GET /purchases/orders/<pk>/print/?is_draft=true|false

    Streams the PDF directly to the client — nothing saved to disk.
    - is_draft=true  → shows DRAFT watermark (all authenticated users)
    - is_draft=false → clean order (admin/superuser only)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        is_draft_param = request.query_params.get("is_draft", "false").lower() == "true"

        # Normal users can ONLY print the draft-watermarked version
        if not is_draft_param and not request.user.is_staff:
            return Response(
                {"detail": "Normal users can only print the draft version."},
                status=status.HTTP_403_FORBIDDEN,
            )

        pdf_bytes, filename = generate_purchase_order_pdf_bytes(order_id=pk, is_draft=is_draft_param)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


class PurchaseOrderSavePDFView(generics.CreateAPIView):
    """POST /purchases/orders/<pk>/pdf/save/ — admin/superuser only"""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SavePurchaseOrderPDFRequestSerializer

    def create(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order     = get_purchase_order_by_id(pk)
        file_name = serializer.validated_data.get("file_name") or order.order_number
        saved     = save_purchase_order_pdf(order_id=pk, file_name=file_name, user=request.user)
        return Response(
            SavedPurchaseOrderPDFSerializer(saved, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class PurchaseOrderSavedPDFListView(generics.ListAPIView):
    """GET /purchases/orders/<pk>/pdf/ — list saved PDFs for an order"""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SavedPurchaseOrderPDFSerializer

    def get_queryset(self):
        return get_saved_pdfs_for_order(self.kwargs["pk"])

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx


class SavedPurchaseOrderPDFDeleteView(generics.DestroyAPIView):
    """DELETE /purchases/pdf/<saved_pdf_id>/"""
    permission_classes = [IsAdminOrSuperuser]

    def destroy(self, request, saved_pdf_id):
        delete_purchase_order_pdf(saved_pdf_id=saved_pdf_id, user=request.user)
        return Response({"detail": "PDF deleted."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Inventory (read for all auth users)
# ---------------------------------------------------------------------------

class InventoryListView(generics.ListAPIView):
    """
    GET /purchases/inventory/
    Available to all authenticated users (including normal users).

    Filter params:
        search      : product name or code (partial match)
        category    : category id
        shelf       : shelf id

    Stats cards moved to GET /purchases/inventory/stats/ (O(1) singleton
    read) — the old embedded stats re-scanned the filtered queryset three
    extra times on every page load.
    """
    permission_classes = [IsAdminOrSuperuserOrReadOnly]
    serializer_class   = InventoryReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_inventory(
            search      = p.get("search"),
            category_id = p.get("category"),
        )


class InventoryStatsView(APIView):
    """
    GET /purchases/inventory/stats/
    O(1) whole-inventory stats for the Inventory page cards — reads the
    InventoryStatsFlow singleton (kept in sync at write time). Global
    numbers by design: cards always show the full picture; the breakdown
    endpoints handle filtered drill-downs.
    """
    permission_classes = [IsAdminOrSuperuserOrReadOnly]

    def get(self, request):
        return Response(InventoryStatsSerializer(get_inventory_stats()).data)


class LowStockInventoryListView(generics.ListAPIView):
    """
    GET /purchases/inventory/low-stock/
    Breakdown behind the "Low Stock" card (0 < quantity <= threshold).
    Same filters as the main inventory list: search, category, shelf.
    """
    permission_classes = [IsAdminOrSuperuserOrReadOnly]
    serializer_class   = InventoryReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_low_stock_inventory(
            search      = p.get("search"),
            category_id = p.get("category"),
        )


class OutOfStockInventoryListView(generics.ListAPIView):
    """
    GET /purchases/inventory/out-of-stock/
    Breakdown behind the "Out of Stock" card (quantity <= 0).
    Same filters as the main inventory list: search, category, shelf.
    """
    permission_classes = [IsAdminOrSuperuserOrReadOnly]
    serializer_class   = InventoryReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_out_of_stock_inventory(
            search      = p.get("search"),
            category_id = p.get("category"),
        )


class InventoryRetrieveView(generics.RetrieveAPIView):
    permission_classes = [IsAdminOrSuperuserOrReadOnly]
    serializer_class   = InventoryReadSerializer

    def get_object(self):
        return get_inventory_by_product_id(self.kwargs["product_id"])


# ---------------------------------------------------------------------------
# Outstanding payable views
# ---------------------------------------------------------------------------

from .selectors import get_all_outstanding_orders, get_outstanding_orders_for_supplier


class SupplierOutstandingOrdersView(generics.ListAPIView):
    """
    GET /purchases/suppliers/<pk>/outstanding-orders/
    Bill-wise breakdown of outstanding payable for ONE supplier.
    Shows every confirmed order that still has payable_outstanding > 0.

    Example: Supplier "Ali Traders" has 3 orders with remaining debt:
      PO-2026-0001: 15,000 remaining
      PO-2026-0003: 8,500 remaining
      PO-2026-0007: 32,000 remaining
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = PurchaseOrderReadSerializer

    def get_queryset(self):
        return get_outstanding_orders_for_supplier(supplier_id=self.kwargs["pk"])


class AllOutstandingOrdersView(generics.ListAPIView):
    """
    GET /purchases/orders/outstanding/
    All confirmed orders with payable_outstanding > 0, across ALL suppliers.
    Full filter support.

    Query params:
        supplier_name   : partial match on supplier name
        supplier_code   : partial match on supplier code
        payment_status  : partial | unpaid  (paid orders won't appear since outstanding > 0)
        date_from       : YYYY-MM-DD
        date_to         : YYYY-MM-DD
        min_outstanding : minimum payable_outstanding amount
        max_outstanding : maximum payable_outstanding amount
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = PurchaseOrderReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_outstanding_orders(
            supplier_name   = p.get("supplier_name"),
            supplier_code   = p.get("supplier_code"),
            payment_status  = p.get("payment_status"),
            date_from       = p.get("date_from"),
            date_to         = p.get("date_to"),
            min_outstanding = p.get("min_outstanding"),
            max_outstanding = p.get("max_outstanding"),
        )


# ---------------------------------------------------------------------------
# Global supplier payment search
# ---------------------------------------------------------------------------

from .selectors import get_all_supplier_payments


class AllSupplierPaymentsView(AllocationsListMixin, generics.ListAPIView):
    """
    GET /purchases/payments/
    Search all supplier payments across all orders.

    Query params:
        reference     : SPY reference number (partial match)
        supplier_name : partial match
        supplier_code : partial match
        method        : cash | jazzcash | easypaisa | bank
        date_from     : YYYY-MM-DD
        date_to       : YYYY-MM-DD
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = SupplierPaymentReadSerializer
    allocations_source_model = "purchases.supplierpayment"
    allocations_context_key  = "supplier_payment_allocations"

    def get_queryset(self):
        p = self.request.query_params
        return get_all_supplier_payments(
            reference     = p.get("reference"),
            supplier_name = p.get("supplier_name"),
            supplier_code = p.get("supplier_code"),
            method        = p.get("method"),
            date_from     = p.get("date_from"),
            date_to       = p.get("date_to"),
        )


# ---------------------------------------------------------------------------
# Lost Inventory (admin/superuser only)
# ---------------------------------------------------------------------------

class LostInventoryListCreateView(generics.ListCreateAPIView):
    """
    GET  /purchases/lost-inventory/  — all lost inventory records, newest first
    POST /purchases/lost-inventory/  — mark one or more products as lost

    Filter params for GET:
        search, product_id, product_name, product_code, reason,
        date, date_from, date_to, min_amount, max_amount
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return LostInventoryCreateSerializer if self.request.method == "POST" else LostInventoryReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_lost_inventory_records(
            search       = p.get("search"),
            product_id   = p.get("product_id"),
            product_name = p.get("product_name"),
            product_code = p.get("product_code"),
            reason       = p.get("reason"),
            date         = p.get("date"),
            date_from    = p.get("date_from"),
            date_to      = p.get("date_to"),
            min_amount   = p.get("min_amount"),
            max_amount   = p.get("max_amount"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d   = serializer.validated_data
        obj = create_lost_inventory_record(
            items=d["items"],
            note=d.get("note", ""),
            user=request.user,
        )
        return Response(LostInventoryReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class LostInventoryRetrieveView(generics.RetrieveAPIView):
    """GET /purchases/lost-inventory/<pk>/"""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = LostInventoryReadSerializer

    def get_object(self):
        return get_lost_inventory_record_by_id(self.kwargs["pk"])


class LostInventoryFifoPreviewView(APIView):
    """
    GET /purchases/lost-inventory/fifo-preview/?product_id=<id>&quantity=<n>
    Read-only preview of the blended FIFO cost for marking a product lost,
    shown on the lost-inventory page before submission. Consumes no stock.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        query = LostInventoryFifoPreviewQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        d = query.validated_data

        from .selectors import get_product_by_id
        get_product_by_id(d["product_id"])  # 404s if the product doesn't exist

        preview = get_fifo_cost_preview(product_id=d["product_id"], quantity=d["quantity"])
        return Response(LostInventoryFifoPreviewSerializer(preview).data)


class MarkLostInventoryFoundView(APIView):
    """
    POST /purchases/lost-inventory/items/<item_id>/found/
    body: {"quantity": <n>}
    Marks part or all of a previously lost item as found again — restores
    stock to its original FIFO batch(es) and reduces the net lost-inventory
    worth shown on the dashboard.
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, item_id):
        serializer = MarkLostInventoryFoundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        item = mark_lost_inventory_found(
            lost_item_id=item_id,
            quantity=serializer.validated_data["quantity"],
            shelf_allocations=[
                {"shelf_id": a["shelf_id"], "quantity": a["quantity"]}
                for a in serializer.validated_data.get("shelf_allocations", [])
            ],
            user=request.user,
        )
        return Response(LostInventoryItemReadSerializer(item).data)


# ---------------------------------------------------------------------------
# Purchase item / return item shelf allocations
# ---------------------------------------------------------------------------

class SetPurchaseItemShelfAllocationsView(APIView):
    """POST /purchases/purchase-items/<pk>/shelf-allocations/"""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, pk):
        serializer = SetShelfAllocationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        set_purchase_item_shelf_allocations(
            purchase_item_id=pk,
            allocations=[{"shelf_id": a["shelf_id"], "quantity": a["quantity"]} for a in d["allocations"]],
            user=request.user,
        )
        # Re-fetch through the allocations-prefetching selector — the object
        # returned by the service doesn't carry the prefetch the read
        # serializer's shelf_allocations/allocated_quantity fields need.
        obj = get_purchase_item_with_allocations_by_id(pk)
        return Response(PurchaseItemReadSerializer(obj).data)


class SetPurchaseReturnItemShelfAllocationsView(APIView):
    """POST /purchases/return-items/<pk>/shelf-allocations/"""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, pk):
        serializer = SetShelfAllocationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        set_purchase_return_item_shelf_allocations(
            return_item_id=pk,
            allocations=[{"shelf_id": a["shelf_id"], "quantity": a["quantity"]} for a in d["allocations"]],
            user=request.user,
        )
        obj = get_purchase_return_item_with_allocations_by_id(pk)
        return Response(PurchaseReturnItemReadSerializer(obj).data)