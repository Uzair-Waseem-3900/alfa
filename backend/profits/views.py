from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsAdminOrSuperuser


def _as_splits(method_allocations):
    """MethodAllocationInputSerializer's validated_data is a list of
    {"payment_method": <PaymentMethod>, "amount": Decimal} dicts — services
    take [(payment_method, amount), ...] tuples."""
    if not method_allocations:
        return None
    return [(d["payment_method"], d["amount"]) for d in method_allocations]
from .selectors import (
    get_all_investor_profit_payouts,
    get_all_monthly_profits,
    get_all_owner_profit_payouts,
    get_current_month_profit,
    get_investor_monthly_shares,
    get_investor_profit_payout_by_id,
    get_monthly_profit_by_period,
    get_net_profit_trend,
    get_owner_profit_payout_by_id,
    get_ownership_split,
    get_profit_flow_stats,
)
from .serializers import (
    CurrentMonthProfitSerializer,
    InvestorMonthlyShareListItemSerializer,
    InvestorProfitPayoutDetailSerializer,
    InvestorProfitPayoutListItemSerializer,
    InvestorProfitPayoutReadSerializer,
    InvestorProfitPayoutWriteSerializer,
    MonthlyProfitDetailSerializer,
    MonthlyProfitListSerializer,
    NetProfitTrendItemSerializer,
    OwnerProfitPayoutListItemSerializer,
    OwnerProfitPayoutReadSerializer,
    OwnerProfitPayoutWriteSerializer,
    OwnershipSplitSerializer,
    ProfitFlowStatsSerializer,
)
from .services import (
    create_investor_profit_payout,
    create_owner_profit_payout,
    delete_investor_profit_payout,
    delete_owner_profit_payout,
)


class BusinessWorthView(APIView):
    """
    GET /profits/business-worth/
    Total business worth (a live net-worth read, not a stored figure) plus
    the ownership split between every investor (by their theoretical,
    growth-compounded current_worth) and the owner (the residual).
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        data = get_ownership_split()
        serializer = OwnershipSplitSerializer(data)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Monthly Profit
# ---------------------------------------------------------------------------

class MonthlyProfitListView(generics.ListAPIView):
    """
    GET /profits/monthly/
    Every finalized month, newest first. Running catch-up first (see
    profits.services.catch_up_monthly_profits) means this always includes
    every month up through the last fully-completed one, with no cron job.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = MonthlyProfitListSerializer

    def get_queryset(self):
        return get_all_monthly_profits(year=self.request.query_params.get("year"))


class CurrentMonthProfitView(APIView):
    """
    GET /profits/monthly/current/
    Live, provisional figures for the still-open current month — never
    stored, always recomputed. No settle actions apply to this period.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        data = get_current_month_profit()
        serializer = CurrentMonthProfitSerializer(data)
        return Response(serializer.data)


class MonthlyProfitDetailView(APIView):
    """
    GET /profits/monthly/<period>/
    Full breakdown for one finalized month, plus every investor's snapshotted
    share and their full payout history.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, period):
        from payment_methods.selectors import get_allocations_by_source_ids

        obj = get_monthly_profit_by_period(period)

        # Batch-fetch every payout's allocations in 2 queries total (one per
        # source model), NOT one per payout — the prefetched payout ids come
        # straight from get_monthly_profit_by_period's cache, no extra query
        # to gather them. Threaded through context so the nested read
        # serializers look these up instead of querying per object.
        investor_payout_ids = [
            p.id for share in obj.investor_shares.all() for p in share.payouts.all()
        ]
        owner_payout_ids = [p.id for p in obj.owner_share.payouts.all()] if hasattr(obj, "owner_share") else []

        context = {
            "investor_payout_allocations": get_allocations_by_source_ids(
                "profits.investorprofitpayout", investor_payout_ids,
            ),
            "owner_payout_allocations": get_allocations_by_source_ids(
                "profits.ownerprofitpayout", owner_payout_ids,
            ),
        }
        serializer = MonthlyProfitDetailSerializer(obj, context=context)
        return Response(serializer.data)


class NetProfitTrendView(APIView):
    """
    GET /profits/net-profit-trend/?months=12
    Cheap read straight off stored MonthlyProfit rows — powers the
    dashboard's Net Profit Trend chart, no live aggregation.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        try:
            months = int(request.query_params.get("months", 12))
        except (TypeError, ValueError):
            months = 12
        months = max(1, min(months, 120))
        data = get_net_profit_trend(months=months)
        serializer = NetProfitTrendItemSerializer(data, many=True)
        return Response(serializer.data)


class ProfitFlowStatsView(APIView):
    """
    GET /profits/stats/
    All-time lifetime profit totals — O(1) after catch-up.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        data = get_profit_flow_stats()
        serializer = ProfitFlowStatsSerializer(data)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# InvestorProfitPayout
# ---------------------------------------------------------------------------

class InvestorProfitPayoutCreateView(APIView):
    """
    POST /profits/monthly/shares/<share_id>/payouts/
    Settles part or all of one investor's share for one month — either a
    real payout (cash out, capital account untouched) or a reinvest (cash
    out then immediately back in as a genuine new investment).
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, share_id):
        serializer = InvestorProfitPayoutWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        payout = create_investor_profit_payout(
            share_id=share_id,
            amount=d["amount"],
            action_type=d["action_type"],
            payout_date=d["payout_date"],
            method_allocations=_as_splits(d.get("method_allocations")),
            note=d.get("note", ""),
            user=request.user,
        )
        return Response(InvestorProfitPayoutReadSerializer(payout).data, status=status.HTTP_201_CREATED)


class InvestorProfitPayoutRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    """
    GET    /profits/payouts/<pk>/
    DELETE /profits/payouts/<pk>/ — reverses cash_in_hand, the share's
    settled amounts, and (for a reinvest) the linked InvestorTransaction too.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = InvestorProfitPayoutDetailSerializer

    def get_object(self):
        return get_investor_profit_payout_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_investor_profit_payout(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Payout reversed and cash in hand restored."}, status=status.HTTP_200_OK)


class InvestorProfitPayoutListView(generics.ListAPIView):
    """
    GET /profits/payouts/
    Every profit settlement ever recorded (payout or reinvest), across every
    investor and month, newest-created first. Capital withdrawals are never
    included — see get_all_investor_profit_payouts docstring.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = InvestorProfitPayoutListItemSerializer

    def get_queryset(self):
        return get_all_investor_profit_payouts()


# ---------------------------------------------------------------------------
# OwnerProfitPayout — exact mirror of InvestorProfitPayout views
# ---------------------------------------------------------------------------

class OwnerProfitPayoutCreateView(APIView):
    """
    POST /profits/monthly/owner-share/<owner_share_id>/payouts/
    Settles part or all of the owner's share for one month — either a real
    payout (cash out) or a reinvest (cash out then immediately back in as a
    genuine owner contribution).
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, owner_share_id):
        serializer = OwnerProfitPayoutWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        payout = create_owner_profit_payout(
            owner_share_id=owner_share_id,
            amount=d["amount"],
            action_type=d["action_type"],
            payout_date=d["payout_date"],
            method_allocations=_as_splits(d.get("method_allocations")),
            note=d.get("note", ""),
            user=request.user,
        )
        return Response(OwnerProfitPayoutReadSerializer(payout).data, status=status.HTTP_201_CREATED)


class OwnerProfitPayoutRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    """
    GET    /profits/owner-payouts/<pk>/
    DELETE /profits/owner-payouts/<pk>/ — reverses cash_in_hand, the share's
    settled amounts, and (for a reinvest) the linked OwnerTransaction too.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = OwnerProfitPayoutReadSerializer

    def get_object(self):
        return get_owner_profit_payout_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_owner_profit_payout(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Payout reversed and cash in hand restored."}, status=status.HTTP_200_OK)


class OwnerProfitPayoutListView(generics.ListAPIView):
    """
    GET /profits/owner-payouts/
    Every owner profit settlement ever recorded, newest-created first.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = OwnerProfitPayoutListItemSerializer

    def get_queryset(self):
        return get_all_owner_profit_payouts()


# ---------------------------------------------------------------------------
# Per-investor profit view
# ---------------------------------------------------------------------------

class InvestorMonthlySharesListView(generics.ListAPIView):
    """
    GET /profits/investors/<investor_id>/shares/
    One investor's profit share across every finalized month, newest first —
    feeds the per-investor profit page's month-by-month settle list.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = InvestorMonthlyShareListItemSerializer

    def get_queryset(self):
        return get_investor_monthly_shares(self.kwargs["investor_id"])
