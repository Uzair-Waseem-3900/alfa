from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from payment_methods.mixins import AllocationsListMixin, as_splits as _as_splits
from payment_methods.selectors import get_allocations_by_source_ids

from .permissions import IsAdminOrSuperuser
from .selectors import (
    get_all_asset_categories,
    get_all_asset_disposals,
    get_all_asset_payments,
    get_all_assets,
    get_asset_by_id,
    get_asset_category_by_id,
    get_asset_payment_by_id,
    get_asset_stats,
    get_asset_valuation_entries,
)
from .serializers import (
    AssetCategoryCreateSerializer,
    AssetCategoryReadSerializer,
    AssetCategoryUpdateSerializer,
    AssetCreateSerializer,
    AssetDisposalReadSerializer,
    AssetDisposeSerializer,
    AssetPaymentReadSerializer,
    AssetReadSerializer,
    AssetRevalueSerializer,
    AssetStatsSerializer,
    AssetValuationEntryReadSerializer,
)
from .services import create_asset, create_asset_category, dispose_asset, revalue_asset, update_asset_category


def _batch_asset_payment_allocations(page_rows) -> dict:
    """AssetPayment rows can point at either assets.asset or
    assets.assetdisposal via source_model/source_id — batch-fetch each
    distinct source_model separately (at most 2, never per-row), then key
    the combined result by AssetPayment.id (not source_id, which is NOT
    unique across the two source tables)."""
    ids_by_model = {}
    for p in page_rows:
        ids_by_model.setdefault(p.source_model, []).append(p.source_id)

    by_model = {
        source_model: get_allocations_by_source_ids(source_model, source_ids)
        for source_model, source_ids in ids_by_model.items()
    }
    return {
        p.id: by_model.get(p.source_model, {}).get(p.source_id, [])
        for p in page_rows
    }


# ---------------------------------------------------------------------------
# Asset stats
# ---------------------------------------------------------------------------

class AssetStatsView(APIView):
    """
    GET /assets/stats/
    Runs catch-up depreciation for every active asset, then returns the
    pre-synced AssetFlow totals — always current, no cron/celery involved.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        stats = get_asset_stats()
        serializer = AssetStatsSerializer(stats)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# AssetCategory
# ---------------------------------------------------------------------------

class AssetCategoryListCreateView(generics.ListCreateAPIView):
    """
    GET  /assets/categories/
    POST /assets/categories/  — valuation_method is set once here and can never change.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return AssetCategoryCreateSerializer if self.request.method == "POST" else AssetCategoryReadSerializer

    def get_queryset(self):
        return get_all_asset_categories(search=self.request.query_params.get("search"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = create_asset_category(**serializer.validated_data, user=request.user)
        return Response(AssetCategoryReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class AssetCategoryRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """
    GET   /assets/categories/<pk>/
    PATCH /assets/categories/<pk>/  — name/depreciation_rate only, valuation_method is immutable.
    """
    permission_classes = [IsAdminOrSuperuser]
    http_method_names  = ["get", "patch"]

    def get_serializer_class(self):
        return AssetCategoryUpdateSerializer if self.request.method == "PATCH" else AssetCategoryReadSerializer

    def get_object(self):
        return get_asset_category_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = update_asset_category(pk=self.kwargs["pk"], user=request.user, **serializer.validated_data)
        return Response(AssetCategoryReadSerializer(obj).data)


# ---------------------------------------------------------------------------
# Asset
# ---------------------------------------------------------------------------

class AssetListCreateView(AllocationsListMixin, generics.ListCreateAPIView):
    """
    GET  /assets/items/  — every active/disposed asset, catch-up run per item
    POST /assets/items/  — register an existing or new asset

    Filter params for GET:
        category_id, acquisition_type (existing|new), is_disposed (true|false), search
    """
    permission_classes = [IsAdminOrSuperuser]
    allocations_source_model = "assets.asset"
    allocations_context_key  = "asset_allocations"

    def get_serializer_class(self):
        return AssetCreateSerializer if self.request.method == "POST" else AssetReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_assets(
            category_id      = p.get("category_id"),
            acquisition_type = p.get("acquisition_type"),
            is_disposed       = p.get("is_disposed"),
            search            = p.get("search"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = create_asset(
            name                = d["name"],
            category_id         = d["category"].pk,
            acquisition_type    = d["acquisition_type"],
            cost                = d["cost"],
            acquisition_date    = d["acquisition_date"],
            method_allocations  = _as_splits(d.get("method_allocations")),
            note                = d.get("note", ""),
            user                = request.user,
        )
        return Response(AssetReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class AssetRetrieveView(generics.RetrieveAPIView):
    """GET /assets/items/<pk>/ — runs catch-up before returning."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = AssetReadSerializer

    def get_object(self):
        return get_asset_by_id(self.kwargs["pk"])


class AssetValuationEntryListView(generics.ListAPIView):
    """
    GET /assets/items/valuation-entries/?asset_id=<id>
    Read-only history — every depreciation/revaluation entry ever posted.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = AssetValuationEntryReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_asset_valuation_entries(
            asset_id   = p.get("asset_id"),
            entry_type = p.get("entry_type"),
        )


class AssetRevalueView(APIView):
    """
    POST /assets/items/<pk>/revalue/
    Manual revaluation — only for revaluation-method categories (e.g. Land).
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, pk):
        serializer = AssetRevalueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        entry = revalue_asset(
            asset_id          = pk,
            new_worth          = d["new_worth"],
            revaluation_date   = d["revaluation_date"],
            note               = d.get("note", ""),
            user               = request.user,
        )
        return Response(AssetValuationEntryReadSerializer(entry).data, status=status.HTTP_201_CREATED)


class AssetDisposeView(APIView):
    """
    POST /assets/items/<pk>/dispose/
    Scrapped: no cash movement. Sold: cash_in_hand increases, gain/loss computed.
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, pk):
        serializer = AssetDisposeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        disposal = dispose_asset(
            asset_id            = pk,
            disposal_type       = d["disposal_type"],
            disposal_date       = d["disposal_date"],
            sale_amount         = d.get("sale_amount"),
            method_allocations  = _as_splits(d.get("method_allocations")),
            reason              = d.get("reason", ""),
            user                = request.user,
        )
        return Response(AssetDisposalReadSerializer(disposal).data, status=status.HTTP_201_CREATED)


class AssetDisposalListView(AllocationsListMixin, generics.ListAPIView):
    """
    GET /assets/disposals/ — every disposal record, newest first.

    Filter params: disposal_type (scrapped|sold), category_id
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = AssetDisposalReadSerializer
    allocations_source_model = "assets.assetdisposal"
    allocations_context_key  = "asset_disposal_allocations"

    def get_queryset(self):
        p = self.request.query_params
        return get_all_asset_disposals(
            disposal_type = p.get("disposal_type"),
            category_id   = p.get("category_id"),
        )


# ---------------------------------------------------------------------------
# AssetPayment — unified purchases+sales feed
# ---------------------------------------------------------------------------

class AssetPaymentListView(generics.ListAPIView):
    """
    GET /assets/payments/ — every real cash-moving asset event (purchases
    AND sales), newest first, from the AssetPayment event table.

    Filter params: payment_type (purchase|sale), date_from, date_to, search
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = AssetPaymentReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_asset_payments(
            payment_type = p.get("payment_type"),
            date_from    = p.get("date_from"),
            date_to      = p.get("date_to"),
            search       = p.get("search"),
        )

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset
        context = self.get_serializer_context()
        context["asset_payment_allocations"] = _batch_asset_payment_allocations(rows)
        serializer = self.get_serializer(rows, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class AssetPaymentRetrieveView(generics.RetrieveAPIView):
    """GET /assets/payments/<pk>/ — single asset payment, by id."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = AssetPaymentReadSerializer

    def get_object(self):
        return get_asset_payment_by_id(self.kwargs["pk"])
