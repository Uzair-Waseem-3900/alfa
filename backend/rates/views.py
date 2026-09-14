from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from purchases.serializers import ProductReadSerializer

from .pdf_service import generate_rate_list_pdf_bytes
from .permissions import IsAdminOrSuperuser, IsAdminOrSuperuserOrReadOnly
from .selectors import (
    get_all_rates,
    get_history_for_product,
    get_rate_by_id,
    get_unpriced_products,
)
from .serializers import (
    ProductCostSerializer,
    ProductRateCreateSerializer,
    ProductRateHistorySerializer,
    ProductRateReadSerializer,
    ProductRateUpdateSerializer,
)
from .services import create_rate, update_rate


# ---------------------------------------------------------------------------
# Rate list: GET (all users) + POST (admin/superuser)
# ---------------------------------------------------------------------------

class ProductRateListCreateView(generics.ListCreateAPIView):
    """
    GET  /rates/              — list all current rates with filters + search
    POST /rates/              — set a rate for a new product

    Query params for GET:
        search      : product name or code (partial, case-insensitive)
        category    : category id
        min_price   : minimum selling price
        max_price   : maximum selling price
    """

    permission_classes = [IsAdminOrSuperuserOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProductRateCreateSerializer
        return ProductRateReadSerializer

    def get_queryset(self):
        params = self.request.query_params
        return get_all_rates(
            search=params.get("search"),
            category_id=params.get("category"),
            min_price=params.get("min_price"),
            max_price=params.get("max_price"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        rate = create_rate(
            product_id=d["product_id"],
            selling_price=d["selling_price"],
            user=request.user,
            note=d.get("note", ""),
        )
        return Response(ProductRateReadSerializer(rate).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Single rate: GET + PATCH (product field is immutable after creation)
# ---------------------------------------------------------------------------

class ProductRateRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """
    GET   /rates/<pk>/        — retrieve a single rate
    PATCH /rates/<pk>/        — update selling price (admin/superuser only)

    Product is intentionally immutable after creation.
    To change the product, delete this rate and create a new one.
    """

    permission_classes = [IsAdminOrSuperuserOrReadOnly]
    http_method_names = ["get", "patch"]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return ProductRateUpdateSerializer
        return ProductRateReadSerializer

    def get_object(self):
        return get_rate_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        rate = update_rate(
            pk=self.kwargs["pk"],
            selling_price=d["selling_price"],
            user=request.user,
            note=d.get("note", ""),
        )
        return Response(ProductRateReadSerializer(rate).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Rate list — print
# ---------------------------------------------------------------------------

class RateListPrintView(APIView):
    """
    GET /rates/print/?search=&category=&min_price=&max_price=

    Streams the PDF directly — nothing saved to disk. Only currently-priced
    products print (same source as the on-screen list — get_all_rates reads
    ProductRate directly, so unpriced products are structurally excluded),
    filtered by the exact params the list page was showing when printed.
    """
    permission_classes = [IsAdminOrSuperuserOrReadOnly]

    def get(self, request):
        params = request.query_params
        pdf_bytes, filename = generate_rate_list_pdf_bytes(
            search=params.get("search"),
            category_id=params.get("category"),
            min_price=params.get("min_price"),
            max_price=params.get("max_price"),
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Unpriced products — products with no rate set yet, browsed/searched
# independently of the (already paginated) rates list above.
# ---------------------------------------------------------------------------

class UnpricedProductListView(generics.ListAPIView):
    """
    GET /rates/unpriced/       — products with no ProductRate yet

    Query params:
        search   : product name or code (partial, case-insensitive)
        category : category id
    """

    permission_classes = [IsAdminOrSuperuserOrReadOnly]
    serializer_class = ProductReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_unpriced_products(search=p.get("search"), category_id=p.get("category"))


# ---------------------------------------------------------------------------
# Rate history for a specific product
# ---------------------------------------------------------------------------

class ProductRateHistoryView(generics.ListAPIView):
    """
    GET /rates/history/<product_id>/
    Returns full price change history for a product, newest first.
    Accessible to all authenticated users — useful for transparency.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ProductRateHistorySerializer

    def get_queryset(self):
        return get_history_for_product(product_id=self.kwargs["product_id"])


# ---------------------------------------------------------------------------
# Product cost (COGS) — shown in the set/edit-price modal while an
# admin/superuser is choosing a selling price. Read-only, no side effects.
# ---------------------------------------------------------------------------

class ProductCostView(APIView):
    """
    GET /rates/cost/<product_id>/
    Reads the stored, frozen-through-returns purchases.Inventory
    .avg_unit_cost directly — same figure the Inventory Valuation report
    already shows for this product. Admin/superuser only (stricter than
    the price-history endpoint above): cost is more sensitive than price
    history, and this is only ever called from the already-admin-only
    price-editing modal.
    """

    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, product_id):
        from purchases.models import Inventory
        from purchases.selectors import get_product_by_id

        get_product_by_id(product_id)  # 404s if missing/deleted
        inv = Inventory.objects.filter(product_id=product_id).first()
        data = {
            "quantity_on_hand": inv.quantity if inv else 0,
            "avg_unit_cost": inv.avg_unit_cost if inv else 0,
            "has_stock": bool(inv and inv.quantity > 0),
        }
        return Response(ProductCostSerializer(data).data)