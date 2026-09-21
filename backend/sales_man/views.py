from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .permissions import IsAdminOrSuperuser
from .selectors import get_all_link_names, get_all_sales_men, get_sales_man_by_id
from .serializers import (
    SalesManLinkNameCreateSerializer,
    SalesManLinkNameReadSerializer,
    SalesManReadSerializer,
    SalesManWriteSerializer,
)
from .services import create_link_name, create_sales_man, delete_link_name, delete_sales_man, update_sales_man


# ---------------------------------------------------------------------------
# SalesMan
# ---------------------------------------------------------------------------

class SalesManListCreateView(generics.ListCreateAPIView):
    """
    GET  /sales-man/sales-men/         — list, ?search= across name/code
    POST /sales-man/sales-men/         — create (admin/superuser only)
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return SalesManWriteSerializer if self.request.method == "POST" else SalesManReadSerializer

    def get_queryset(self):
        return get_all_sales_men(search=self.request.query_params.get("search"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        sales_man = create_sales_man(
            name=d["name"], code=d["code"], address=d.get("address", ""),
            phone=d.get("phone", ""), user=request.user,
        )
        return Response(SalesManReadSerializer(sales_man).data, status=status.HTTP_201_CREATED)


class SalesManRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /sales-man/sales-men/<pk>/
    PATCH  /sales-man/sales-men/<pk>/   — name, code, address, phone only
    DELETE /sales-man/sales-men/<pk>/   — only when every link name has zero customers
    """
    permission_classes = [IsAdminOrSuperuser]
    http_method_names = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return SalesManWriteSerializer if self.request.method == "PATCH" else SalesManReadSerializer

    def get_object(self):
        return get_sales_man_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        sales_man = update_sales_man(pk=self.kwargs["pk"], user=request.user, **serializer.validated_data)
        return Response(SalesManReadSerializer(sales_man).data)

    def destroy(self, request, *args, **kwargs):
        delete_sales_man(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Sales man deleted."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# SalesManLinkName — nested under a sales man
# ---------------------------------------------------------------------------

class SalesManLinkNameListCreateView(generics.ListCreateAPIView):
    """
    GET  /sales-man/sales-men/<sales_man_id>/link-names/
    POST /sales-man/sales-men/<sales_man_id>/link-names/  — add a new link name
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return SalesManLinkNameCreateSerializer if self.request.method == "POST" else SalesManLinkNameReadSerializer

    def get_queryset(self):
        return get_all_link_names(sales_man_id=self.kwargs["sales_man_id"])

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        link_name = create_link_name(
            sales_man_id=self.kwargs["sales_man_id"],
            name=serializer.validated_data["name"], user=request.user,
        )
        return Response(SalesManLinkNameReadSerializer(link_name).data, status=status.HTTP_201_CREATED)


class SalesManLinkNameDestroyView(generics.DestroyAPIView):
    """
    DELETE /sales-man/link-names/<pk>/  — only when zero customers assigned.
    """
    permission_classes = [IsAdminOrSuperuser]

    def destroy(self, request, *args, **kwargs):
        delete_link_name(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Link name deleted."}, status=status.HTTP_200_OK)


class SalesManLinkNameOptionsView(generics.ListAPIView):
    """
    GET /sales-man/link-names/
    Flat, read-only list of every active link name across all sales men —
    the dropdown source for the customer create/edit form. Deliberately
    IsAuthenticated (not admin-only): billing customer create/update is
    IsAuthenticated too (CustomerListCreateView), and every such user must
    be able to pick a link name to compose the customer's code. Not
    paginated — bounded by "number of sales men * link names each", the
    same small-dataset exception as the suppliers list (see frontend.md).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SalesManLinkNameReadSerializer
    pagination_class = None

    def get_queryset(self):
        return get_all_link_names()


# ---------------------------------------------------------------------------
# Sales man's customers / invoices — reuse billing's existing selectors and
# serializers (DRY: no duplicate selector/UI-shape, per architecture.md).
# ---------------------------------------------------------------------------

class SalesManCustomerListView(generics.ListAPIView):
    """GET /sales-man/sales-men/<sales_man_id>/customers/"""
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        from billing.serializers import CustomerReadSerializer
        return CustomerReadSerializer

    def get_queryset(self):
        from billing.selectors import get_all_customers

        get_sales_man_by_id(self.kwargs["sales_man_id"])  # 404 if missing
        p = self.request.query_params
        return get_all_customers(
            search=p.get("search"), name=p.get("name"), code=p.get("code"),
            sales_man_id=self.kwargs["sales_man_id"],
        )


class SalesManInvoiceListView(generics.ListAPIView):
    """
    GET /sales-man/sales-men/<sales_man_id>/invoices/
    Same filter set as billing's invoice list (get_filtered_invoices),
    scoped to this sales man's customers.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        from billing.serializers import InvoiceReadSerializer
        return InvoiceReadSerializer

    def get_queryset(self):
        from billing.selectors import get_filtered_invoices

        get_sales_man_by_id(self.kwargs["sales_man_id"])  # 404 if missing
        p = self.request.query_params
        return get_filtered_invoices(
            sales_man_id   = self.kwargs["sales_man_id"],
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
            due_only       = p.get("due_only") in ("true", "True", "1"),
            outstanding_only = p.get("outstanding_only") in ("true", "True", "1"),
        )
