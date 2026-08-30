from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .selectors import get_credit_score_history, get_customer_credit_score, get_customers_by_tier
from .serializers import CreditScoreHistorySerializer, CustomerCreditScoreSerializer


class CreditCustomerReportView(generics.ListAPIView):
    """
    GET /credit-score/customers/?tier=good|average|poor&search=...

    Backs the Credit Customer Report's three tier-filter buttons. Any
    authenticated user can view (see credit_score.permissions docstring —
    edits are gated at the billing layer, not here).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerCreditScoreSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_customers_by_tier(tier=p.get("tier"), search=p.get("search"))


class CustomerCreditScoreDetailView(generics.RetrieveAPIView):
    """GET /credit-score/customers/<customer_id>/ — current score + breakdown."""
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerCreditScoreSerializer

    def get_object(self):
        return get_customer_credit_score(self.kwargs["customer_id"])


class CustomerCreditScoreHistoryView(generics.ListAPIView):
    """GET /credit-score/customers/<customer_id>/history/ — paginated event log."""
    permission_classes = [IsAuthenticated]
    serializer_class = CreditScoreHistorySerializer

    def get_queryset(self):
        return get_credit_score_history(self.kwargs["customer_id"])
