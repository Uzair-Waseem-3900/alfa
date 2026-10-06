"""Reads for the purchase requests this software has made (see models.PurchaseRequest)."""

from django.db.models import Count, IntegerField, OuterRef, Prefetch, QuerySet, Subquery
from django.db.models.functions import Coalesce

from purchases.models import Product

from .models import PurchaseRequest, PurchaseRequestItem, PurchaseRequestShelf


def list_purchase_requests(*, status: str = None) -> QuerySet:
    """Newest first. The item count is a correlated subquery, not a GROUP BY over every request."""
    qs = PurchaseRequest.objects.select_related("created_by").annotate(
        item_count=Coalesce(Subquery(
            PurchaseRequestItem.objects.filter(request=OuterRef("pk"))
            .order_by().values("request").annotate(n=Count("pk")).values("n"),
            output_field=IntegerField(),
        ), 0)
    )
    if status and status in PurchaseRequest.Status.values:
        qs = qs.filter(status=status)
    return qs


def get_purchase_request(pk: int):
    """One request with its items and (this software's own) shelf plan — fixed number of queries."""
    return (
        PurchaseRequest.objects.select_related("created_by")
        .prefetch_related(
            Prefetch(
                "items",
                queryset=PurchaseRequestItem.objects.prefetch_related(
                    Prefetch("shelves", queryset=PurchaseRequestShelf.objects.select_related("shelf"))
                ),
            )
        )
        .filter(pk=pk)
        .first()
    )


def get_local_products_by_code(codes) -> dict:
    """{code: Product} for the given codes — one query for a whole page of search results."""
    return {p.code: p for p in Product.objects.filter(code__in=list(codes), is_deleted=False)}
