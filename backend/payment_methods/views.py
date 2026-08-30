from rest_framework import generics, status
from rest_framework.response import Response

from .mixins import AllocationsListMixin
from .permissions import IsAdminOrSuperuser
from .selectors import (
    get_account_transfer_by_id,
    get_all_account_transfers,
    get_all_payment_methods,
    get_payment_method_allocations,
    get_payment_method_by_id,
)
from .serializers import (
    AccountTransferReadSerializer,
    AccountTransferWriteSerializer,
    PaymentAllocationReadSerializer,
    PaymentMethodReadSerializer,
    PaymentMethodWriteSerializer,
)
from .services import (
    create_method, delete_account_transfer, soft_delete_method,
    transfer_between_methods, update_method,
)


class PaymentMethodListCreateView(generics.ListCreateAPIView):
    """
    GET  /payment-methods/  — all accounts (Cash + any user-created ones)
    POST /payment-methods/  — create a new account

    Filter params for GET:
        search
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return PaymentMethodWriteSerializer if self.request.method == "POST" else PaymentMethodReadSerializer

    def get_queryset(self):
        return get_all_payment_methods(search=self.request.query_params.get("search"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = create_method(**serializer.validated_data, user=request.user)
        return Response(PaymentMethodReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class PaymentMethodRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /payment-methods/<pk>/
    PATCH  /payment-methods/<pk>/  — name/account_number only; blocked on the protected Cash row
    DELETE /payment-methods/<pk>/  — blocked unless balance is exactly 0; blocked on the protected Cash row
    """
    permission_classes = [IsAdminOrSuperuser]
    http_method_names   = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return PaymentMethodWriteSerializer if self.request.method == "PATCH" else PaymentMethodReadSerializer

    def get_object(self):
        return get_payment_method_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = update_method(pk=self.kwargs["pk"], user=request.user, **serializer.validated_data)
        return Response(PaymentMethodReadSerializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        soft_delete_method(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Payment method deleted."}, status=status.HTTP_200_OK)


class PaymentMethodAllocationListView(generics.ListAPIView):
    """
    GET /payment-methods/<pk>/allocations/
    Read-only transaction history for one method — every active
    PaymentAllocation row it has ever been part of.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class    = PaymentAllocationReadSerializer

    def get_queryset(self):
        return get_payment_method_allocations(payment_method_id=self.kwargs["pk"])


# ---------------------------------------------------------------------------
# AccountTransfer (Phase 6)
# ---------------------------------------------------------------------------

class AccountTransferListCreateView(AllocationsListMixin, generics.ListCreateAPIView):
    """
    GET  /payment-methods/transfers/  — every transfer, newest first
    POST /payment-methods/transfers/  — move balance directly from one
         method to another; never touches cash_in_hand

    Filter params for GET: from_method_id, to_method_id
    """
    permission_classes = [IsAdminOrSuperuser]
    allocations_source_model = "payment_methods.accounttransfer"
    allocations_context_key  = "account_transfer_allocations"

    def get_serializer_class(self):
        return AccountTransferWriteSerializer if self.request.method == "POST" else AccountTransferReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_account_transfers(
            from_method_id=p.get("from_method_id"), to_method_id=p.get("to_method_id"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = transfer_between_methods(
            from_method_id = d["from_method"].pk,
            to_method_id   = d["to_method"].pk,
            amount         = d["amount"],
            date           = d["date"],
            note           = d.get("note", ""),
            user           = request.user,
        )
        return Response(AccountTransferReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class AccountTransferRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    """
    GET    /payment-methods/transfers/<pk>/
    DELETE /payment-methods/transfers/<pk>/ — reverses both methods' balances
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class    = AccountTransferReadSerializer

    def get_object(self):
        return get_account_transfer_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_account_transfer(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Transfer reversed and both balances restored."}, status=status.HTTP_200_OK)
