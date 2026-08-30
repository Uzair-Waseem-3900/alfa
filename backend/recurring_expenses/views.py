from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from payment_methods.mixins import AllocationsListMixin, as_splits as _as_splits

from .permissions import IsAdminOrSuperuser
from .selectors import (
    get_all_recurring_expense_assignments,
    get_all_recurring_expense_categories,
    get_all_recurring_expense_monthly_stats,
    get_all_recurring_expense_payments,
    get_all_recurring_expenses,
    get_pending_recurring_expenses,
    get_recurring_expense_assignment_by_id,
    get_recurring_expense_by_id,
    get_recurring_expense_category_by_id,
    get_recurring_expense_flow_stats,
    get_recurring_expense_monthly_stats_by_period,
    get_recurring_expense_payment_by_id,
)
from .serializers import (
    RecurringExpenseAssignmentBulkCreateSerializer,
    RecurringExpenseAssignmentCreateSerializer,
    RecurringExpenseAssignmentPaymentReadSerializer,
    RecurringExpenseAssignmentPaymentWriteSerializer,
    RecurringExpenseAssignmentReadSerializer,
    RecurringExpenseCategoryReadSerializer,
    RecurringExpenseCategoryWriteSerializer,
    RecurringExpenseFlowStatsSerializer,
    RecurringExpenseMonthlyStatsSerializer,
    RecurringExpenseReadSerializer,
    RecurringExpenseWriteSerializer,
)
from .services import (
    bulk_create_recurring_expense_assignments,
    create_recurring_expense,
    create_recurring_expense_assignment,
    create_recurring_expense_category,
    create_recurring_expense_payment,
    delete_recurring_expense,
    delete_recurring_expense_assignment,
    delete_recurring_expense_category,
    delete_recurring_expense_payment,
    update_recurring_expense,
    update_recurring_expense_category,
)


# ---------------------------------------------------------------------------
# RecurringExpenseCategory
# ---------------------------------------------------------------------------

class RecurringExpenseCategoryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return RecurringExpenseCategoryWriteSerializer if self.request.method == "POST" else RecurringExpenseCategoryReadSerializer

    def get_queryset(self):
        return get_all_recurring_expense_categories(search=self.request.query_params.get("search"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = create_recurring_expense_category(**serializer.validated_data, user=request.user)
        return Response(RecurringExpenseCategoryReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class RecurringExpenseCategoryRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrSuperuser]
    http_method_names  = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return RecurringExpenseCategoryWriteSerializer if self.request.method == "PATCH" else RecurringExpenseCategoryReadSerializer

    def get_object(self):
        return get_recurring_expense_category_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = update_recurring_expense_category(pk=self.kwargs["pk"], user=request.user, **serializer.validated_data)
        return Response(RecurringExpenseCategoryReadSerializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        delete_recurring_expense_category(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Category deleted. Previously assigned expenses are unaffected."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# RecurringExpense (template)
# ---------------------------------------------------------------------------

class RecurringExpenseListCreateView(generics.ListCreateAPIView):
    """
    Filter params for GET: search, category_id, is_active
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return RecurringExpenseWriteSerializer if self.request.method == "POST" else RecurringExpenseReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_recurring_expenses(
            search=p.get("search"), category_id=p.get("category_id"), is_active=p.get("is_active"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = create_recurring_expense(
            name=d["name"], category_id=d["category"].id, amount=d["amount"],
            start_date=d["start_date"], note=d.get("note", ""), user=request.user,
        )
        return Response(RecurringExpenseReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class RecurringExpenseRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrSuperuser]
    http_method_names  = ["get", "patch", "delete"]

    def get_serializer_class(self):
        return RecurringExpenseWriteSerializer if self.request.method == "PATCH" else RecurringExpenseReadSerializer

    def get_object(self):
        return get_recurring_expense_by_id(self.kwargs["pk"])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = update_recurring_expense(
            pk=self.kwargs["pk"],
            name=d.get("name"), category_id=d["category"].id if "category" in d else None,
            amount=d.get("amount"), start_date=d.get("start_date"),
            is_active=d.get("is_active"), note=d.get("note"),
            user=request.user,
        )
        return Response(RecurringExpenseReadSerializer(obj).data)

    def destroy(self, request, *args, **kwargs):
        delete_recurring_expense(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Recurring expense deleted. Past assignments/payments are unaffected."}, status=status.HTTP_200_OK)


class RecurringExpensePendingDuesView(generics.ListAPIView):
    """
    GET /recurring-expenses/pending-dues/?period=YYYY-MM&category_id=
    Active templates with no assignment yet for the given period — feeds the
    Post Dues screen.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = RecurringExpenseReadSerializer

    def get_queryset(self):
        period = self.request.query_params.get("period")
        if not period:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"period": "This query param is required (YYYY-MM)."})
        return get_pending_recurring_expenses(period=period, category_id=self.request.query_params.get("category_id"))


# ---------------------------------------------------------------------------
# RecurringExpenseAssignment
# ---------------------------------------------------------------------------

class RecurringExpenseAssignmentListCreateView(generics.ListCreateAPIView):
    """
    Filter params for GET: recurring_expense_id, period, category_id, payment_status, search
    """
    permission_classes = [IsAdminOrSuperuser]

    def get_serializer_class(self):
        return RecurringExpenseAssignmentCreateSerializer if self.request.method == "POST" else RecurringExpenseAssignmentReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_recurring_expense_assignments(
            recurring_expense_id=p.get("recurring_expense_id"), period=p.get("period"),
            category_id=p.get("category_id"), payment_status=p.get("payment_status"),
            search=p.get("search"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = create_recurring_expense_assignment(
            recurring_expense_id=d["recurring_expense"].id, period=d["period"], user=request.user,
        )
        return Response(RecurringExpenseAssignmentReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class RecurringExpenseAssignmentBulkCreateView(APIView):
    """
    POST /recurring-expenses/assignments/bulk/  { period, category_id? }
    Assigns every active, not-yet-assigned template for the period (optionally
    scoped to one category). Each is attempted independently.
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request):
        serializer = RecurringExpenseAssignmentBulkCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        result = bulk_create_recurring_expense_assignments(
            period=d["period"], category_id=d.get("category_id"), user=request.user,
        )
        return Response({
            "created": RecurringExpenseAssignmentReadSerializer(result["created"], many=True).data,
            "failed": result["failed"],
        }, status=status.HTTP_201_CREATED)


class RecurringExpenseAssignmentRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    """
    GET    /recurring-expenses/assignments/<pk>/
    DELETE /recurring-expenses/assignments/<pk>/ — unassign a mistaken
    posting. Only allowed while it's still fully unpaid (no payments
    recorded); rejected with a 400 otherwise.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = RecurringExpenseAssignmentReadSerializer

    def get_object(self):
        return get_recurring_expense_assignment_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_recurring_expense_assignment(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Assignment unassigned."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# RecurringExpenseAssignmentPayment
# ---------------------------------------------------------------------------

class RecurringExpenseAssignmentPaymentListCreateView(AllocationsListMixin, generics.ListCreateAPIView):
    """Filter params for GET: assignment_id, date_from, date_to"""
    permission_classes = [IsAdminOrSuperuser]
    allocations_source_model = "recurring_expenses.recurringexpenseassignmentpayment"
    allocations_context_key  = "recurring_expense_payment_allocations"

    def get_serializer_class(self):
        return RecurringExpenseAssignmentPaymentWriteSerializer if self.request.method == "POST" else RecurringExpenseAssignmentPaymentReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_all_recurring_expense_payments(
            assignment_id=p.get("assignment_id"), date_from=p.get("date_from"), date_to=p.get("date_to"),
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data
        obj = create_recurring_expense_payment(
            assignment_id=d["assignment"].id, amount=d["amount"],
            payment_date=d["payment_date"], method_allocations=_as_splits(d["method_allocations"]),
            note=d.get("note", ""), user=request.user,
        )
        return Response(RecurringExpenseAssignmentPaymentReadSerializer(obj).data, status=status.HTTP_201_CREATED)


class RecurringExpenseAssignmentPaymentRetrieveDestroyView(generics.RetrieveDestroyAPIView):
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = RecurringExpenseAssignmentPaymentReadSerializer

    def get_object(self):
        return get_recurring_expense_payment_by_id(self.kwargs["pk"])

    def destroy(self, request, *args, **kwargs):
        delete_recurring_expense_payment(pk=self.kwargs["pk"], user=request.user)
        return Response({"detail": "Payment deleted and all balances restored."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class RecurringExpenseFlowStatsView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        stats = get_recurring_expense_flow_stats()
        return Response(RecurringExpenseFlowStatsSerializer(stats).data)


class RecurringExpenseMonthlyStatsListView(generics.ListAPIView):
    """Filter params for GET: is_fully_paid"""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = RecurringExpenseMonthlyStatsSerializer

    def get_queryset(self):
        return get_all_recurring_expense_monthly_stats(is_fully_paid=self.request.query_params.get("is_fully_paid"))


class RecurringExpenseMonthlyStatsDetailView(APIView):
    """GET /recurring-expenses/monthly-stats/<period>/ — zeroed if nothing posted yet that month."""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, period):
        data = get_recurring_expense_monthly_stats_by_period(period)
        return Response(RecurringExpenseMonthlyStatsSerializer(data).data)
