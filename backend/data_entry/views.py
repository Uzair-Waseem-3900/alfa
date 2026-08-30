from rest_framework import generics, status
from rest_framework.response import Response

from .permissions import IsSuperuser
from .selectors import (
    get_all_customer_opening_balances,
    get_all_opening_cash_entries,
    get_all_opening_investor_investments,
    get_all_opening_stock_orders,
    get_all_supplier_opening_balances,
)
from .serializers import (
    CustomerOpeningBalanceReadSerializer,
    CustomerOpeningBalanceWriteSerializer,
    OpeningCashReadSerializer,
    OpeningCashWriteSerializer,
    OpeningInvestorInvestmentReadSerializer,
    OpeningInvestorInvestmentWriteSerializer,
    OpeningStockOrderReadSerializer,
    OpeningStockWriteSerializer,
    SupplierOpeningBalanceReadSerializer,
    SupplierOpeningBalanceWriteSerializer,
)
from .services import (
    create_customer_opening_balance,
    create_opening_cash,
    create_opening_investor_investment,
    create_opening_stock,
    create_supplier_opening_balance,
)


# ---------------------------------------------------------------------------
# Feature 1 — Supplier Opening Balance
# ---------------------------------------------------------------------------

class SupplierOpeningBalanceListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/data-entry/supplier-opening-balance/   list all (audit)
    POST /api/data-entry/supplier-opening-balance/   create (permanent lock)
    """
    permission_classes = [IsSuperuser]

    def get_serializer_class(self):
        return (SupplierOpeningBalanceWriteSerializer if self.request.method == "POST"
                else SupplierOpeningBalanceReadSerializer)

    def get_queryset(self):
        return get_all_supplier_opening_balances()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = create_supplier_opening_balance(**serializer.validated_data, user=request.user)
        return Response(SupplierOpeningBalanceReadSerializer(obj).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Feature 2 — Customer Opening Balance
# ---------------------------------------------------------------------------

class CustomerOpeningBalanceListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/data-entry/customer-opening-balance/   list all (audit)
    POST /api/data-entry/customer-opening-balance/   create (permanent lock)
    """
    permission_classes = [IsSuperuser]

    def get_serializer_class(self):
        return (CustomerOpeningBalanceWriteSerializer if self.request.method == "POST"
                else CustomerOpeningBalanceReadSerializer)

    def get_queryset(self):
        return get_all_customer_opening_balances()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = create_customer_opening_balance(**serializer.validated_data, user=request.user)
        return Response(CustomerOpeningBalanceReadSerializer(obj).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Feature 3 — Opening Cash
# ---------------------------------------------------------------------------

class OpeningCashListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/data-entry/opening-cash/   list all cash entries
    POST /api/data-entry/opening-cash/   add cash to cash_in_hand
    """
    permission_classes = [IsSuperuser]

    def get_serializer_class(self):
        return OpeningCashWriteSerializer if self.request.method == "POST" else OpeningCashReadSerializer

    def get_queryset(self):
        return get_all_opening_cash_entries()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = create_opening_cash(**serializer.validated_data, user=request.user)
        return Response(OpeningCashReadSerializer(obj).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Feature 4 — Opening Stock
# ---------------------------------------------------------------------------

class OpeningStockListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/data-entry/opening-stock/   list all opening-stock orders
    POST /api/data-entry/opening-stock/   add opening stock
    """
    permission_classes = [IsSuperuser]

    def get_serializer_class(self):
        return OpeningStockWriteSerializer if self.request.method == "POST" else OpeningStockOrderReadSerializer

    def get_queryset(self):
        return get_all_opening_stock_orders()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_opening_stock(items=serializer.validated_data["items"], user=request.user)
        return Response(OpeningStockOrderReadSerializer(order).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Feature 5 — Opening Investor Investment
# ---------------------------------------------------------------------------

class OpeningInvestorInvestmentListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/data-entry/opening-investor-investment/   list all (audit)
    POST /api/data-entry/opening-investor-investment/   record investor capital (no cash impact)
    """
    permission_classes = [IsSuperuser]

    def get_serializer_class(self):
        return (OpeningInvestorInvestmentWriteSerializer if self.request.method == "POST"
                else OpeningInvestorInvestmentReadSerializer)

    def get_queryset(self):
        return get_all_opening_investor_investments()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        txn = create_opening_investor_investment(**serializer.validated_data, user=request.user)
        return Response(OpeningInvestorInvestmentReadSerializer(txn).data, status=status.HTTP_201_CREATED)
