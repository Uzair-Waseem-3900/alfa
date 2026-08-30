from django.shortcuts import get_object_or_404

from backend.search import search_q

from .models import AccountTransfer, PaymentAllocation, PaymentMethod


def get_all_payment_methods(*, search: str = None):
    qs = PaymentMethod.objects.all()
    if search:
        qs = qs.filter(search_q(search, "name"))
    return qs


def get_payment_method_by_id(pk: int) -> PaymentMethod:
    return get_object_or_404(PaymentMethod, pk=pk, is_deleted=False)


def get_payment_method_allocations(*, payment_method_id: int):
    """Read-only transaction history for one method — every active
    PaymentAllocation row that method has ever been part of, newest first."""
    return PaymentAllocation.objects.filter(
        payment_method_id=payment_method_id, is_deleted=False,
    ).order_by("-date", "-created_at")


def get_allocations_for_source(source):
    """Every active PaymentAllocation row for one transaction (a Payment,
    SupplierPayment, ...) — the real split, for read serializers to show
    alongside the derived legacy `method` label."""
    from .services import _source_label
    return PaymentAllocation.objects.filter(
        source_model=_source_label(source), source_id=source.pk, is_deleted=False,
    ).select_related("payment_method").order_by("id")


def get_allocations_by_source_ids(source_model: str, source_ids):
    """Batched version of get_allocations_for_source, for list/nested
    contexts (e.g. a month's full payout history) — ONE query instead of
    one per row. Returns {source_id: [allocation, ...]}. Callers thread
    the result through serializer context so nested read serializers can
    look up their own row's allocations instead of querying per object."""
    if not source_ids:
        return {}
    by_id = {}
    for alloc in PaymentAllocation.objects.filter(
        source_model=source_model, source_id__in=list(source_ids), is_deleted=False,
    ).select_related("payment_method").order_by("id"):
        by_id.setdefault(alloc.source_id, []).append(alloc)
    return by_id


def get_all_account_transfers(*, from_method_id: int = None, to_method_id: int = None):
    qs = AccountTransfer.objects.filter(is_deleted=False).select_related(
        "from_method", "to_method", "created_by",
    )
    if from_method_id:
        qs = qs.filter(from_method_id=from_method_id)
    if to_method_id:
        qs = qs.filter(to_method_id=to_method_id)
    return qs


def get_account_transfer_by_id(pk: int) -> AccountTransfer:
    return get_object_or_404(
        AccountTransfer.objects.select_related("from_method", "to_method", "created_by"),
        pk=pk, is_deleted=False,
    )
