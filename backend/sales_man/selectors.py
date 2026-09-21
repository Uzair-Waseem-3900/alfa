from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from backend.search import search_q

from .models import SalesMan, SalesManLinkName


def _clean(value):
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


# ---------------------------------------------------------------------------
# SalesMan
# ---------------------------------------------------------------------------

def get_all_sales_men(*, search: str = None) -> QuerySet:
    # link_names prefetched — every list/detail row shows its link names,
    # without this it's one extra query per row (N+1).
    qs = SalesMan.objects.filter(is_deleted=False).prefetch_related("link_names")
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name", "code"))
    return qs


def get_sales_man_by_id(pk: int) -> SalesMan:
    return get_object_or_404(
        SalesMan.objects.prefetch_related("link_names"), pk=pk, is_deleted=False,
    )


# ---------------------------------------------------------------------------
# SalesManLinkName
# ---------------------------------------------------------------------------

def get_all_link_names(*, sales_man_id: int = None) -> QuerySet:
    qs = SalesManLinkName.objects.filter(is_deleted=False).select_related("sales_man")
    if _clean(sales_man_id):
        qs = qs.filter(sales_man_id=_clean(sales_man_id))
    return qs


def get_link_name_by_id(pk: int) -> SalesManLinkName:
    return get_object_or_404(
        SalesManLinkName.objects.select_related("sales_man"), pk=pk, is_deleted=False,
    )


def get_link_name_by_name(name: str) -> SalesManLinkName:
    return get_object_or_404(
        SalesManLinkName.objects.select_related("sales_man"),
        name__iexact=name, is_deleted=False,
    )
