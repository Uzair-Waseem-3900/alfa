from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from payment_methods.mixins import AllocationsListMixin, as_splits as _as_splits

from .permissions import IsAdminOrSuperuser
from .selectors import (
    get_all_cash_adjustments,
    get_all_investor_transactions,
    get_all_investors,
    get_all_owner_transactions,
    get_cash_adjustment_by_id,
    get_cash_management_stats,
    get_investor_by_id,
    get_investor_transaction_by_id,
    get_investor_valuation_entries,
    get_owner_transaction_by_id,
)
from .serializers import (
    CashAdjustmentReadSerializer,
    CashAdjustmentWriteSerializer,
    CashManagementStatsSerializer,
    InvestorReadSerializer,
    InvestorTransactionReadSerializer,
    InvestorTransactionWriteSerializer,
    InvestorValuationEntryReadSerializer,
    InvestorWriteSerializer,
    OwnerTransactionReadSerializer,
    OwnerTransactionWriteSerializer,
)
from .services import (
    create_cash_adjustment,
    create_investor,
    create_investor_transaction,
    create_owner_transaction,
    delete_cash_adjustment,
    delete_investor,
    delete_investor_transaction,
    delete_owner_transaction,
    update_investor,
)


# ---------------------------------------------------------------------------
# Cash management stats
# ---------------------------------------------------------------------------

class CashManagementStatsView(APIView):
    """
    GET /cash-management/stats/
    Returns the store's current cash-reconciliation and investor-capital
    position. No runtime aggregation — reads from the pre-synced
    CashManagementFlow model.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        stats = get_cash_management_stats()
        serializer = CashManagementStatsSerializer(stats)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# CashAdjustment
# ---------------------------------------------------------------------------

class CashAdjustmentListCreateView(AllocationsListMixin, generics.ListCreateAPIView):
    """
    GET  /cash-management/adjustments/  — all lost/found cash entries, newest first
    POST /cash-management/adjustments/  — record a new lost or found cash entry

    Filter params for GET:
        adjustment_type (lost|found), search, date_from, date_to, min_amount, max_amount
    """
    permission_classes = [IsAdminOrSuperuser]
    allocations_source_model = "cash_management.cashadjustment"
    allocations_context_key  = "cash_adjustment_allocations"

    def get_serializer_class(self):
        return CashAdjustmentWriteSerializer if self.request.method == "POST" else CashAdjustmentReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_cash_adjustments(
            adjustment_type = p.get("adjustment_type"),
            search          = p.get("search"),
            date_from       = p.get("date_from"),
            date_to         = p.get("date_to"),
            min_amount      = p.get("min_amount"),
            max_amount      = p.get("max_amount"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = create_cash_adjustment(
            amount             = d["amount"],
            adjustment_type    = d["adjustment_type"],
            adjustment_date    = d["adjustment_date"],
            method_allocations = _as_splits(d["method_allocations"]),
            reason             = d.get("reason", ""),
            user               = request.user,
        )
        return Response(CashAdjustmentReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class CashAdjustmentRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    """
    GET    /cash-management/adjustments/<pk>/
    DELETE /cash-management/adjustments/<pk>/
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = CashAdjustmentReadSerializer

    def get_object(self):
        return get_cash_adjustment_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_cash_adjustment(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Cash adjustment deleted and cash in hand restored."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Investor
# ---------------------------------------------------------------------------

class InvestorListCreateView(generics.ListCreateAPIView):
    """
    GET  /cash-management/investors/  — all investors
    POST /cash-management/investors/  — create a new investor

    Filter params for GET:
        search
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return InvestorWriteSerializer if self.request.method == "POST" else InvestorReadSerializer

    def get_queryset(self):
        return get_all_investors(search=self.request.query_params.get("search"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = create_investor(**serializer.validated_data, user=request.user)
        return Response(InvestorReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class InvestorRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /cash-management/investors/<pk>/
    PATCH  /cash-management/investors/<pk>/  — name/contact info only, not financial totals
    DELETE /cash-management/investors/<pk>/  — blocked if the investor has recorded transactions
    """
    permission_classes = [IsAdminOrSuperuser]
    http_method_names  = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return InvestorWriteSerializer if self.request.method == "PATCH" else InvestorReadSerializer

    def get_object(self):
        return get_investor_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = update_investor(pk=self.kwargs["pk"], user=request.user, **serializer.validated_data)
        return Response(InvestorReadSerializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        delete_investor(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Investor deleted."}, status=status.HTTP_200_OK)


class InvestorValuationEntryListView(generics.ListAPIView):
    """
    GET /cash-management/investors/valuation-entries/?investor_id=<id>
    Read-only growth history — every monthly compounding entry ever posted.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = InvestorValuationEntryReadSerializer

    def get_queryset(self):
        return get_investor_valuation_entries(investor_id=self.request.query_params.get("investor_id"))


# ---------------------------------------------------------------------------
# InvestorTransaction
# ---------------------------------------------------------------------------

class InvestorTransactionListCreateView(AllocationsListMixin, generics.ListCreateAPIView):
    """
    GET  /cash-management/investor-transactions/  — all investment/withdrawal events
    POST /cash-management/investor-transactions/  — record a new investment or withdrawal

    Filter params for GET:
        investor_id, transaction_type (investment|withdrawal), search,
        date_from, date_to, min_amount, max_amount
    """
    permission_classes = [IsAdminOrSuperuser]
    allocations_source_model = "cash_management.investortransaction"
    allocations_context_key  = "investor_transaction_allocations"

    def get_serializer_class(self):
        return InvestorTransactionWriteSerializer if self.request.method == "POST" else InvestorTransactionReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_investor_transactions(
            investor_id      = p.get("investor_id"),
            transaction_type = p.get("transaction_type"),
            search           = p.get("search"),
            date_from        = p.get("date_from"),
            date_to          = p.get("date_to"),
            min_amount       = p.get("min_amount"),
            max_amount       = p.get("max_amount"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = create_investor_transaction(
            investor_id        = d["investor"].pk,
            transaction_type   = d["transaction_type"],
            amount             = d["amount"],
            transaction_date   = d["transaction_date"],
            method_allocations = _as_splits(d["method_allocations"]),
            note               = d.get("note", ""),
            user               = request.user,
        )
        return Response(InvestorTransactionReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class InvestorTransactionRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    """
    GET    /cash-management/investor-transactions/<pk>/
    DELETE /cash-management/investor-transactions/<pk>/
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = InvestorTransactionReadSerializer

    def get_object(self):
        return get_investor_transaction_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_investor_transaction(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Investor transaction deleted and balances restored."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# OwnerTransaction
# ---------------------------------------------------------------------------

class OwnerTransactionListCreateView(AllocationsListMixin, generics.ListCreateAPIView):
    """
    GET  /cash-management/owner-transactions/  — all owner contribution/drawing events
    POST /cash-management/owner-transactions/  — record a new owner contribution or drawing

    Filter params for GET:
        transaction_type (contribution|drawing), search, date_from, date_to, min_amount, max_amount
    """
    permission_classes = [IsAdminOrSuperuser]
    allocations_source_model = "cash_management.ownertransaction"
    allocations_context_key  = "owner_transaction_allocations"

    def get_serializer_class(self):
        return OwnerTransactionWriteSerializer if self.request.method == "POST" else OwnerTransactionReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_owner_transactions(
            transaction_type = p.get("transaction_type"),
            search           = p.get("search"),
            date_from        = p.get("date_from"),
            date_to          = p.get("date_to"),
            min_amount       = p.get("min_amount"),
            max_amount       = p.get("max_amount"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = create_owner_transaction(
            transaction_type   = d["transaction_type"],
            amount             = d["amount"],
            transaction_date   = d["transaction_date"],
            method_allocations = _as_splits(d["method_allocations"]),
            note               = d.get("note", ""),
            user               = request.user,
        )
        return Response(OwnerTransactionReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class OwnerTransactionRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    """
    GET    /cash-management/owner-transactions/<pk>/
    DELETE /cash-management/owner-transactions/<pk>/
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = OwnerTransactionReadSerializer

    def get_object(self):
        return get_owner_transaction_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_owner_transaction(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Owner transaction deleted and cash in hand adjusted."}, status=status.HTTP_200_OK)
