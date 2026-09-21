from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import SalesMan, SalesManLinkName
from .selectors import get_link_name_by_id, get_sales_man_by_id


def _soft_delete(instance, user) -> None:
    instance.is_deleted = True
    instance.deleted_at = timezone.now()
    instance.deleted_by = user
    instance.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


# ---------------------------------------------------------------------------
# Stat maintenance — the ONLY writer for SalesMan.total_customers/
# total_outstanding. Called from billing/services.py at every write path
# that changes a customer's sales_man assignment or credit_outstanding.
# `.update(F(...) + delta)` compiles to a single atomic `UPDATE ... SET x =
# x + delta` — Postgres/SQLite apply that server-side per row, so concurrent
# adjustments to the SAME sales_man never lose an update (no select_for_update
# needed here: chaining .update() after a queryset never actually issues the
# SELECT a lock would apply to). This only protects the additive step itself
# — a CALLER that reads a value before deciding what delta to pass (e.g. a
# balance "transfer" between two sales men) is a different hazard and must
# hold its own lock around that read+decide, not rely on this function.
# ---------------------------------------------------------------------------

def _adjust_sales_man_stats(
    *, sales_man_id: int, customer_delta: int = 0, outstanding_delta: Decimal = Decimal("0"),
) -> None:
    if not sales_man_id or (customer_delta == 0 and outstanding_delta == 0):
        return
    SalesMan.objects.filter(pk=sales_man_id).update(
        total_customers=F("total_customers") + customer_delta,
        total_outstanding=F("total_outstanding") + outstanding_delta,
    )


# ---------------------------------------------------------------------------
# SalesMan
# ---------------------------------------------------------------------------

@transaction.atomic
def create_sales_man(*, name: str, code: str, address: str = "", phone: str = "", user) -> SalesMan:
    from rest_framework.exceptions import ValidationError

    duplicate_error = ValidationError({"code": "A sales man with this code already exists."})
    if SalesMan.objects.filter(code__iexact=code, is_deleted=False).exists():
        raise duplicate_error
    try:
        with transaction.atomic():
            return SalesMan.objects.create(
                name=name, code=code.upper(), address=address, phone=phone,
                created_by=user, updated_by=user,
            )
    except IntegrityError:
        # A concurrent request created the same code between the check above
        # and this create — the DB's own unique constraint caught it.
        raise duplicate_error


@transaction.atomic
def update_sales_man(
    *, pk: int, name: str = None, code: str = None,
    address: str = None, phone: str = None, user,
) -> SalesMan:
    """name, code, address, phone are mutable. link_names are never renamed
    or reassigned here — only added/removed via create_link_name/delete_link_name."""
    from rest_framework.exceptions import ValidationError

    sales_man = get_sales_man_by_id(pk)
    duplicate_error = ValidationError({"code": "A sales man with this code already exists."})
    if code:
        qs = SalesMan.objects.filter(code__iexact=code, is_deleted=False).exclude(pk=pk)
        if qs.exists():
            raise duplicate_error
        sales_man.code = code.upper()
    if name is not None:
        sales_man.name = name
    if address is not None:
        sales_man.address = address
    if phone is not None:
        sales_man.phone = phone
    sales_man.updated_by = user
    try:
        with transaction.atomic():
            sales_man.save(update_fields=["name", "code", "address", "phone", "updated_by", "updated_at"])
    except IntegrityError:
        raise duplicate_error
    return sales_man


@transaction.atomic
def delete_sales_man(*, pk: int, user) -> None:
    """
    Only allowed when every non-deleted link name owned by this sales man
    has zero non-deleted customers currently assigned to it. Passing that
    check cascades: soft-deletes the sales man AND all its link names in
    the same transaction.
    """
    from rest_framework.exceptions import ValidationError
    from billing.models import Customer

    sales_man = get_sales_man_by_id(pk)
    link_names = list(sales_man.link_names.filter(is_deleted=False))

    if Customer.objects.filter(sales_man_id=pk, is_deleted=False).exists():
        raise ValidationError({
            "sales_man": (
                "This sales man still has customers assigned to one or more of "
                "his link names. Reassign or remove those customers first."
            )
        })

    for link_name in link_names:
        _soft_delete(link_name, user)
    _soft_delete(sales_man, user)


# ---------------------------------------------------------------------------
# SalesManLinkName
# ---------------------------------------------------------------------------

@transaction.atomic
def create_link_name(*, sales_man_id: int, name: str, user) -> SalesManLinkName:
    from rest_framework.exceptions import ValidationError

    sales_man = get_sales_man_by_id(sales_man_id)
    duplicate_error = ValidationError({"name": "A link name with this name already exists."})
    if SalesManLinkName.objects.filter(name__iexact=name, is_deleted=False).exists():
        raise duplicate_error
    try:
        with transaction.atomic():
            return SalesManLinkName.objects.create(
                sales_man=sales_man, name=name.upper(), created_by=user, updated_by=user,
            )
    except IntegrityError:
        raise duplicate_error


@transaction.atomic
def delete_link_name(*, pk: int, user) -> None:
    """Only allowed when zero non-deleted customers are currently assigned to it."""
    from rest_framework.exceptions import ValidationError
    from billing.models import Customer

    link_name = get_link_name_by_id(pk)
    if Customer.objects.filter(sales_man_link_name_id=pk, is_deleted=False).exists():
        raise ValidationError({
            "link_name": "This link name still has customers assigned to it. Reassign or remove them first."
        })
    _soft_delete(link_name, user)
