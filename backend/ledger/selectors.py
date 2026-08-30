from django.db.models import QuerySet
from django.shortcuts import get_object_or_404

from backend.search import search_q

from .models import CustomerLedger, SavedCustomerLedgerPDF, SavedLedgerPDF, SupplierLedger, SupplierLedgerEntry
from .services import _get_customer_entries_with_running_balance, _get_entries_with_running_balance


def _clean(value):
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def get_all_ledgers(*, search: str = None) -> QuerySet:
    # Hide the internal SYS-OPENING system supplier's ledger from users.
    qs = (
        SupplierLedger.objects.select_related("supplier")
        .filter(is_deleted=False)
        .exclude(supplier_code="SYS-OPENING")
    )
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "supplier_name", "supplier_code"))
    return qs


def get_ledger_by_id(pk: int) -> SupplierLedger:
    return get_object_or_404(
        SupplierLedger.objects.select_related("supplier"), pk=pk, is_deleted=False,
    )


def get_ledger_by_supplier_id(supplier_id: int) -> SupplierLedger:
    return get_object_or_404(SupplierLedger, supplier_id=supplier_id, is_deleted=False)


def get_ledger_entries(
    *,
    ledger         : SupplierLedger,
    date_from      : str = None,
    date_to        : str = None,
    entry_type     : str = None,
    reference      : str = None,
    min_amount     : str = None,
    max_amount     : str = None,
) -> tuple[list[dict], object]:
    """
    Returns (entries_with_running_balance, closing_balance).
    Filters are applied before balance computation where possible.
    Note: running balance always reflects full history up to each entry.

    Takes the ledger OBJECT — every caller has already fetched it (for the
    header of the response), so re-fetching by id here was a wasted query
    per request.
    """
    # Get full running balance entries (hybrid method)
    entries, _opening_balance, closing_balance = _get_entries_with_running_balance(
        ledger=ledger,
        date_from=date_from,
        date_to=date_to,
    )

    # Apply additional in-memory filters (entry_type, reference, amount)
    if _clean(entry_type):
        entries = [e for e in entries if e["entry_type"] == _clean(entry_type)]
    if _clean(reference):
        ref = _clean(reference).lower()
        entries = [e for e in entries if ref in e["reference"].lower()]
    if _clean(min_amount):
        min_v = float(_clean(min_amount))
        entries = [
            e for e in entries
            if float(e["debit"]) >= min_v or float(e["credit"]) >= min_v
        ]
    if _clean(max_amount):
        max_v = float(_clean(max_amount))
        entries = [
            e for e in entries
            if float(e["debit"]) <= max_v or float(e["credit"]) <= max_v
        ]

    return entries, closing_balance


def get_saved_pdfs_for_ledger(ledger_id: int) -> QuerySet:
    return SavedLedgerPDF.objects.filter(
        ledger_id=ledger_id, is_deleted=False,
    ).select_related("saved_by").order_by("-created_at")


# ---------------------------------------------------------------------------
# Customer ledger — mirrors the supplier selectors above.
# ---------------------------------------------------------------------------

def get_all_customer_ledgers(*, search: str = None) -> QuerySet:
    qs = CustomerLedger.objects.select_related("customer").filter(is_deleted=False)
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "customer_name", "customer_code"))
    return qs


def get_customer_ledger_by_id(pk: int) -> CustomerLedger:
    return get_object_or_404(
        CustomerLedger.objects.select_related("customer"), pk=pk, is_deleted=False,
    )


def get_customer_ledger_by_customer_id(customer_id: int) -> CustomerLedger:
    return get_object_or_404(CustomerLedger, customer_id=customer_id, is_deleted=False)


def get_customer_ledger_entries(
    *,
    ledger         : CustomerLedger,
    date_from      : str = None,
    date_to        : str = None,
    entry_type     : str = None,
    reference      : str = None,
    min_amount     : str = None,
    max_amount     : str = None,
) -> tuple[list[dict], object]:
    """
    Returns (entries_with_running_balance, closing_balance). Mirrors
    get_ledger_entries — see that function's docstring.
    """
    entries, _opening_balance, closing_balance = _get_customer_entries_with_running_balance(
        ledger=ledger,
        date_from=date_from,
        date_to=date_to,
    )

    if _clean(entry_type):
        entries = [e for e in entries if e["entry_type"] == _clean(entry_type)]
    if _clean(reference):
        ref = _clean(reference).lower()
        entries = [e for e in entries if ref in e["reference"].lower()]
    if _clean(min_amount):
        min_v = float(_clean(min_amount))
        entries = [
            e for e in entries
            if float(e["debit"]) >= min_v or float(e["credit"]) >= min_v
        ]
    if _clean(max_amount):
        max_v = float(_clean(max_amount))
        entries = [
            e for e in entries
            if float(e["debit"]) <= max_v or float(e["credit"]) <= max_v
        ]

    return entries, closing_balance


def get_saved_pdfs_for_customer_ledger(ledger_id: int) -> QuerySet:
    return SavedCustomerLedgerPDF.objects.filter(
        ledger_id=ledger_id, is_deleted=False,
    ).select_related("saved_by").order_by("-created_at")