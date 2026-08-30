from rest_framework.response import Response


def as_splits(method_allocations):
    """MethodAllocationInputSerializer's validated_data is a list of
    {"payment_method": <PaymentMethod>, "amount": Decimal} dicts — services
    take [(payment_method, amount), ...] tuples, the shape
    payment_methods.services.record_allocations expects."""
    if not method_allocations:
        return None
    return [(d["payment_method"], d["amount"]) for d in method_allocations]


class AllocationsListMixin:
    """
    Shared `list()` override for any ListCreateAPIView whose read serializer
    has an `allocations` SerializerMethodField — batch-fetches the CURRENT
    PAGE's allocations in ONE query and threads it through serializer
    context, instead of each row querying live (architecture.md's STRICT
    O(1)-per-page / <200ms rule). Set `allocations_source_model` (the
    app_label.model_name string) and `allocations_context_key` (must match
    the key the read serializer's get_allocations reads) on the subclass.

    First written for cash_management's three list views (Phase 5 Batch A);
    promoted here once a second app needed the identical override, per
    architecture.md's "generalize before duplicating" rule.
    """
    allocations_source_model = None
    allocations_context_key  = None

    def list(self, request, *args, **kwargs):
        from .selectors import get_allocations_by_source_ids

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset
        context = self.get_serializer_context()
        context[self.allocations_context_key] = get_allocations_by_source_ids(
            self.allocations_source_model, [r.id for r in rows],
        )
        serializer = self.get_serializer(rows, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)
