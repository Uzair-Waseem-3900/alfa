from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from payment_methods.mixins import AllocationsListMixin, as_splits as _as_splits

from .permissions import IsAdminOrSuperuser
from .selectors import (
    get_all_tax_payments,
    get_all_wht_payments,
    get_tax_payment_by_id,
    get_tax_stats,
    get_wht_payment_by_id,
)
from .serializers import (
    TaxPaymentReadSerializer,
    TaxPaymentWriteSerializer,
    TaxStatsSerializer,
    WHTPaymentReadSerializer,
    WHTPaymentWriteSerializer,
)
from .services import create_tax_payment, create_wht_payment, delete_tax_payment, delete_wht_payment


# ---------------------------------------------------------------------------
# Tax position stats
# ---------------------------------------------------------------------------

class TaxStatsView(APIView):
    """
    GET /taxes/stats/
    Returns the store's current sales-tax (GST) and withholding-tax (WHT)
    position. No runtime aggregation — reads from the pre-synced TaxFlow model.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        stats = get_tax_stats()
        serializer = TaxStatsSerializer(stats)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# TaxPayment
# ---------------------------------------------------------------------------

class TaxPaymentListCreateView(AllocationsListMixin, generics.ListCreateAPIView):
    """
    GET  /taxes/payments/  — all GST payments made to FBR, newest first
    POST /taxes/payments/  — record a new GST payment (deducts cash_in_hand)

    Filter params for GET:
        search, date_from, date_to, min_amount, max_amount
    """
    permission_classes = [IsAdminOrSuperuser]
    allocations_source_model = "taxes.taxpayment"
    allocations_context_key  = "tax_payment_allocations"

    def get_serializer_class(self):
        return TaxPaymentWriteSerializer if self.request.method == "POST" else TaxPaymentReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_tax_payments(
            search     = p.get("search"),
            date_from  = p.get("date_from"),
            date_to    = p.get("date_to"),
            min_amount = p.get("min_amount"),
            max_amount = p.get("max_amount"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = create_tax_payment(
            amount             = d["amount"],
            payment_date       = d["payment_date"],
            method_allocations = _as_splits(d["method_allocations"]),
            note               = d.get("note", ""),
            user               = request.user,
        )
        return Response(TaxPaymentReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class TaxPaymentRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    """
    GET    /taxes/payments/<pk>/
    DELETE /taxes/payments/<pk>/
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = TaxPaymentReadSerializer

    def get_object(self):
        return get_tax_payment_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_tax_payment(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Tax payment deleted and cash in hand restored."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# WHTPayment
# ---------------------------------------------------------------------------

class WHTPaymentListCreateView(AllocationsListMixin, generics.ListCreateAPIView):
    """
    GET  /taxes/wht-payments/  — all WHT deposits made to FBR, newest first
    POST /taxes/wht-payments/  — record a new WHT payment (deducts cash_in_hand)

    Filter params for GET:
        search, date_from, date_to, min_amount, max_amount
    """
    permission_classes = [IsAdminOrSuperuser]
    allocations_source_model = "taxes.whtpayment"
    allocations_context_key  = "wht_payment_allocations"

    def get_serializer_class(self):
        return WHTPaymentWriteSerializer if self.request.method == "POST" else WHTPaymentReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_wht_payments(
            search     = p.get("search"),
            date_from  = p.get("date_from"),
            date_to    = p.get("date_to"),
            min_amount = p.get("min_amount"),
            max_amount = p.get("max_amount"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = create_wht_payment(
            amount             = d["amount"],
            payment_date       = d["payment_date"],
            method_allocations = _as_splits(d["method_allocations"]),
            note               = d.get("note", ""),
            user               = request.user,
        )
        return Response(WHTPaymentReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class WHTPaymentRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    """
    GET    /taxes/wht-payments/<pk>/
    DELETE /taxes/wht-payments/<pk>/
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = WHTPaymentReadSerializer

    def get_object(self):
        return get_wht_payment_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_wht_payment(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "WHT payment deleted and cash in hand restored."}, status=status.HTTP_200_OK)
