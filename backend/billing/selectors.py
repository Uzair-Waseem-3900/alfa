from django.db.models import Prefetch, Q, QuerySet
from django.shortcuts import get_object_or_404

from backend.search import search_q

# Shared index-friendly date-range helpers (identical day boundaries to the
# __date lookups they replace, but able to use the created_at indexes).
from purchases.selectors import _day_start, _next_day_start

from .models import (
    Customer, Invoice, InvoiceItem, InvoiceItemShelfAllocation,
    InvoiceReturnItemShelfAllocation, Payment, Return, ReturnItem,
)


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

def get_all_customers(
    *, search: str = None, name: str = None, code: str = None, tier: str = None,
) -> QuerySet:
    # select_related: one JOIN each for credit_score (score/tier column) and
    # created_by/updated_by (CustomerReadSerializer's StringRelatedField
    # fields) — without the latter two, every row on the page fired two
    # separate queries to resolve them (N+1; 25 rows = 50 extra queries,
    # each paying a full network round trip to the DB — measured ~5s of a
    # ~5.4s page load before this fix).
    qs = Customer.objects.filter(is_deleted=False).select_related(
        "credit_score", "created_by", "updated_by",
    )
    if search:
        qs = qs.filter(search_q(search, "name", "code", "mobile"))
    if name:
        qs = qs.filter(search_q(name, "name"))
    if code:
        qs = qs.filter(search_q(code, "code"))
    if tier:
        # credit_score__tier — indexed column on CustomerCreditScore, one JOIN.
        qs = qs.filter(credit_score__tier=tier)
    return qs


def get_customer_by_id(pk: int) -> Customer:
    return get_object_or_404(Customer, pk=pk, is_deleted=False)


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------

def _invoice_qs():
    # Exactly what InvoiceReadSerializer outputs — nothing more:
    #  - customer's audit users + credit_score (CustomerReadSerializer
    #    nests the full customer, including credit_score/credit_tier —
    #    without this JOIN, every row fired its own query for it: N+1)
    #  - items with product (name/code) and product__rate, which the draft
    #    preview reads per item (was a query per item before)
    # Dropped as never-serialized dead weight: items__fifo_layers__purchase
    # (loaded the ENTIRE ever-growing FIFO ledger on every list request),
    # payments, and item category/shelf.
    return Invoice.objects.select_related(
        "customer", "customer__created_by", "customer__updated_by", "customer__credit_score",
        "created_by", "updated_by", "confirmed_by", "deleted_by",
    ).prefetch_related(
        Prefetch(
            "items",
            queryset=InvoiceItem.objects.select_related("product", "product__rate").prefetch_related(
                Prefetch(
                    "shelf_allocations",
                    queryset=InvoiceItemShelfAllocation.objects.select_related("shelf"),
                ),
            ),
        ),
    )


def get_invoice_by_id(pk: int) -> Invoice:
    return get_object_or_404(_invoice_qs(), pk=pk, is_deleted=False)


def get_invoice_by_bill_number(bill_number: str) -> Invoice:
    return get_object_or_404(_invoice_qs(), bill_number=bill_number, is_deleted=False)


# ---------------------------------------------------------------------------
# Invoice Item
# ---------------------------------------------------------------------------

def get_invoice_item_by_id(pk: int) -> InvoiceItem:
    return get_object_or_404(
        InvoiceItem.objects.select_related(
            "invoice", "product",
        ),
        pk=pk,
    )


def get_invoice_item_with_allocations_by_id(pk: int) -> InvoiceItem:
    return get_object_or_404(
        InvoiceItem.objects.select_related("invoice", "product").prefetch_related(
            Prefetch(
                "shelf_allocations",
                queryset=InvoiceItemShelfAllocation.objects.select_related("shelf"),
            ),
        ),
        pk=pk,
    )


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

def get_payments_for_invoice(invoice_id: int, *, reference: str = None) -> QuerySet:
    qs = Payment.objects.filter(
        invoice_id=invoice_id, is_deleted=False
    ).select_related("created_by", "invoice__customer")
    if reference:
        qs = qs.filter(search_q(reference, "reference_number"))
    return qs


def get_all_invoice_payments(
    *,
    reference     : str = None,
    customer_name : str = None,
    customer_code : str = None,
    method        : str = None,
    date_from     : str = None,
    date_to       : str = None,
) -> QuerySet:
    """Search billing payments across all invoices with full filter support."""
    qs = Payment.objects.filter(
        is_deleted=False, amount__gt=0,
    ).select_related("invoice__customer", "created_by").order_by("-payment_date")
    if _clean(reference):
        qs = qs.filter(search_q(_clean(reference), "reference_number"))
    if _clean(customer_name):
        qs = qs.filter(search_q(_clean(customer_name), "invoice__customer__name"))
    if _clean(customer_code):
        qs = qs.filter(search_q(_clean(customer_code), "invoice__customer__code"))
    if _clean(method):
        qs = qs.filter(method=_clean(method))
    if _clean(date_from):
        qs = qs.filter(payment_date__gte=_clean(date_from))
    if _clean(date_to):
        qs = qs.filter(payment_date__lte=_clean(date_to))
    return qs


def get_payment_by_id(pk: int) -> Payment:
    return get_object_or_404(
        Payment.objects.select_related("created_by", "invoice__customer"), pk=pk, is_deleted=False,
    )


# ---------------------------------------------------------------------------
# Return
# ---------------------------------------------------------------------------

_RETURN_ITEM_PREFETCH = Prefetch(
    "items",
    queryset=ReturnItem.objects.select_related(
        "invoice_item__product", "invoice_item__invoice",
    ).prefetch_related(
        Prefetch(
            "shelf_allocations",
            queryset=InvoiceReturnItemShelfAllocation.objects.select_related("shelf"),
        ),
    ),
)


def get_returns_for_invoice(invoice_id: int) -> QuerySet:
    # invoice__customer: the read serializer outputs bill number and
    # customer name on every return — without this it's 2 queries per row.
    return Return.objects.filter(
        invoice_id=invoice_id, is_deleted=False,
    ).select_related("invoice__customer", "created_by", "accepted_by").prefetch_related(
        _RETURN_ITEM_PREFETCH,
    )


def get_all_returns(
    *,
    reference: str = None,
    bill_number: str = None,
    customer_name: str = None,
    status: str = None,
    date_from: str = None,
    date_to: str = None,
) -> QuerySet:
    """Search all returns across all invoices with full filter support."""
    qs = Return.objects.filter(
        is_deleted=False,
    ).select_related("invoice__customer", "created_by", "accepted_by").prefetch_related(
        _RETURN_ITEM_PREFETCH,
    ).order_by("-created_at")

    if _clean(reference):
        qs = qs.filter(search_q(_clean(reference), "reference_number"))
    if _clean(bill_number):
        qs = qs.filter(search_q(_clean(bill_number), "invoice__bill_number"))
    if _clean(customer_name):
        qs = qs.filter(search_q(_clean(customer_name), "invoice__customer__name"))
    if _clean(status):
        qs = qs.filter(status=_clean(status))
    if _clean(date_from):
        start = _day_start(_clean(date_from))
        qs = qs.filter(created_at__gte=start) if start else qs.filter(created_at__date__gte=_clean(date_from))
    if _clean(date_to):
        end = _next_day_start(_clean(date_to))
        qs = qs.filter(created_at__lt=end) if end else qs.filter(created_at__date__lte=_clean(date_to))

    return qs


def get_return_by_id(pk: int) -> Return:
    return get_object_or_404(
        Return.objects.select_related(
            "invoice__customer", "created_by", "accepted_by",
        ).prefetch_related(_RETURN_ITEM_PREFETCH),
        pk=pk,
        is_deleted=False,
    )


def get_return_item_by_id(pk: int) -> ReturnItem:
    return get_object_or_404(
        ReturnItem.objects.select_related(
            "return_record", "invoice_item__product",
        ).prefetch_related(
            Prefetch(
                "shelf_allocations",
                queryset=InvoiceReturnItemShelfAllocation.objects.select_related("shelf"),
            ),
        ),
        pk=pk,
    )


# ---------------------------------------------------------------------------
# FIFO helper — used exclusively by services
# ---------------------------------------------------------------------------

def get_available_purchase_batches(product_id: int, *, for_update: bool = False) -> QuerySet:
    """
    Returns confirmed PurchaseItems for a product that still have remaining stock,
    ordered oldest-confirmed first (FIFO order). Excludes soft-deleted items.
    Uses PurchaseItem (renamed from Purchase) from the purchases app.

    for_update=True locks the batch rows — required for paths that decrement
    remaining_quantity (invoice confirm); read-only checks must not pass it.
    """
    from purchases.selectors import get_available_purchase_items_for_fifo
    return get_available_purchase_items_for_fifo(product_id, for_update=for_update)


# ---------------------------------------------------------------------------
# Payment summary selectors
# ---------------------------------------------------------------------------

def get_invoice_payment_summary(invoice_id: int) -> Invoice:
    """
    Returns a single invoice with full payment breakdown.
    cash_received, credit_outstanding, total_paid, remaining_amount
    are stored fields updated on every payment event.
    """
    # payments prefetched with their created_by (serialized per payment).
    # Payment.objects is the SoftDeleteManager — same filtering the bare
    # "payments" prefetch applied via the related manager. The old
    # items__product prefetch was never serialized here — dropped.
    return get_object_or_404(
        Invoice.objects.select_related("customer").prefetch_related(
            Prefetch("payments", queryset=Payment.objects.select_related("created_by", "invoice__customer")),
        ),
        pk=invoice_id,
        is_deleted=False,
    )


def get_customer_outstanding(customer_id: int) -> dict:
    """
    Returns a payment summary across ALL non-draft invoices for a customer.
    Excludes DRAFT invoices — only invoices that have been confirmed count.

    Uses grand_total (tax-inclusive) as the billing amount.
    If grand_total is 0 on old records (migrated before this field was added),
    falls back to subtotal so results are never misleadingly zero.
    """
    from django.db.models import Sum, Case, When, F
    from decimal import Decimal

    invoices = Invoice.objects.filter(
        customer_id=customer_id,
        is_deleted=False,
    ).exclude(status=Invoice.Status.DRAFT)

    agg = invoices.aggregate(
        total_billed             = Sum("grand_total"),
        total_cash_received      = Sum("cash_received"),
        total_credit_outstanding = Sum("credit_outstanding"),
        total_paid               = Sum("total_paid"),
        total_remaining          = Sum("remaining_amount"),
    )

    return {
        "customer_id"              : customer_id,
        "total_billed"             : agg["total_billed"]             or Decimal("0"),
        "total_cash_received"      : agg["total_cash_received"]      or Decimal("0"),
        "total_credit_outstanding" : agg["total_credit_outstanding"] or Decimal("0"),
        "total_paid"               : agg["total_paid"]               or Decimal("0"),
        "total_remaining"          : agg["total_remaining"]          or Decimal("0"),
    }


def get_customers_with_outstanding(
    *,
    search          : str = None,
    customer_name   : str = None,
    customer_code   : str = None,
    payment_status  : str = None,
    min_outstanding : str = None,
    max_outstanding : str = None,
) -> "QuerySet":
    """
    Lists customers with credit_outstanding > 0, with full filter support.

    Filter params:
        search          : combined name OR code partial match
        customer_name   : name partial match (separate from code)
        customer_code   : code partial match (separate from name)
        payment_status  : unpaid | partial
        min_outstanding : minimum total outstanding
        max_outstanding : maximum total outstanding

    Note: search, customer_name, customer_code can be combined freely.
    """
    from django.db.models import Sum, Q
    from django.db.models.functions import Coalesce
    from django.db.models import DecimalField, Value

    invoice_filter = Q(
        invoices__is_deleted=False,
        invoices__status__in=[
            Invoice.Status.CONFIRMED,
            Invoice.Status.PARTIAL,
            Invoice.Status.RETURNED,
        ],
    )
    if _clean(payment_status):
        invoice_filter &= Q(invoices__payment_status=_clean(payment_status))

    qs = Customer.objects.filter(is_deleted=False).annotate(
        outstanding=Coalesce(
            Sum("invoices__credit_outstanding", filter=invoice_filter),
            Value(0, output_field=DecimalField()),
        )
    ).filter(outstanding__gt=0)

    # Apply name/code filters AFTER annotation so outstanding is still correct
    if _clean(search):
        qs = qs.filter(search_q(_clean(search), "name", "code"))
    if _clean(customer_name):
        qs = qs.filter(search_q(_clean(customer_name), "name"))
    if _clean(customer_code):
        qs = qs.filter(search_q(_clean(customer_code), "code"))
    if _clean(min_outstanding):
        qs = qs.filter(outstanding__gte=_clean(min_outstanding))
    if _clean(max_outstanding):
        qs = qs.filter(outstanding__lte=_clean(max_outstanding))

    return qs.order_by("-outstanding")


# ---------------------------------------------------------------------------
# Invoice filtering selectors
# ---------------------------------------------------------------------------

def _clean(value):
    """Returns None if value is None or empty/whitespace string, else stripped value."""
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped if stripped else None


def get_filtered_invoices(
    *,
    status         : str  = None,
    customer_id    : int  = None,
    customer_name  : str  = None,
    customer_code  : str  = None,
    bill_number    : str  = None,
    date           : str  = None,
    date_from      : str  = None,
    date_to        : str  = None,
    payment_status : str  = None,
    min_amount     : str  = None,
    max_amount     : str  = None,
    due_only       : bool = False,
) -> "QuerySet":
    """
    Master invoice filter selector — all list views use this, including the
    Due Invoices tab (due_only=True): confirmed, still-outstanding invoices
    whose payment_due_date has passed. payment_due_date is a plain DateField
    (not a DateTimeField), so a direct __lte comparison is index-safe —
    no __date cast needed.
    Every parameter is optional; combining them narrows results.
    _clean() ensures empty strings from query params don't slip through.
    """
    qs = _invoice_qs().filter(is_deleted=False)

    if due_only:
        from django.utils import timezone
        # Not just status=CONFIRMED — a partially-returned invoice (status=
        # PARTIAL) can still carry a real outstanding balance past its due
        # date. Only DRAFT invoices (no due-date relevance yet) are excluded.
        qs = qs.exclude(status=Invoice.Status.DRAFT).filter(
            credit_outstanding__gt=0,
            payment_due_date__lte=timezone.localtime(timezone.now()).date(),
        )

    if _clean(status):
        qs = qs.filter(status=_clean(status))
    if _clean(customer_id):
        qs = qs.filter(customer_id=_clean(customer_id))
    if _clean(customer_name):
        qs = qs.filter(search_q(_clean(customer_name), "customer__name"))
    if _clean(customer_code):
        qs = qs.filter(search_q(_clean(customer_code), "customer__code"))
    if _clean(bill_number):
        qs = qs.filter(search_q(_clean(bill_number), "bill_number"))
    if _clean(date):
        start = _day_start(_clean(date))
        end   = _next_day_start(_clean(date))
        if start and end:
            qs = qs.filter(created_at__gte=start, created_at__lt=end)
        else:
            qs = qs.filter(created_at__date=_clean(date))
    if _clean(date_from):
        start = _day_start(_clean(date_from))
        qs = qs.filter(created_at__gte=start) if start else qs.filter(created_at__date__gte=_clean(date_from))
    if _clean(date_to):
        end = _next_day_start(_clean(date_to))
        qs = qs.filter(created_at__lt=end) if end else qs.filter(created_at__date__lte=_clean(date_to))
    if _clean(payment_status):
        qs = qs.filter(payment_status=_clean(payment_status))
    if _clean(min_amount):
        qs = qs.filter(grand_total__gte=_clean(min_amount))
    if _clean(max_amount):
        qs = qs.filter(grand_total__lte=_clean(max_amount))

    return qs


def get_all_outstanding_invoices(
    *,
    customer_name  : str = None,
    customer_code  : str = None,
    payment_status : str = None,
    date_from      : str = None,
    date_to        : str = None,
    min_outstanding: str = None,
    max_outstanding: str = None,
) -> "QuerySet":
    """
    Returns all confirmed invoices with credit_outstanding > 0.
    Supports full filtering. Sorted by highest outstanding first.

    Query params:
        customer_name   : partial match
        customer_code   : partial match
        payment_status  : unpaid | partial
        date_from       : YYYY-MM-DD
        date_to         : YYYY-MM-DD
        min_outstanding : minimum credit_outstanding
        max_outstanding : maximum credit_outstanding
    """
    qs = _invoice_qs().filter(
        is_deleted=False,
        credit_outstanding__gt=0,
    ).exclude(status=Invoice.Status.DRAFT)

    if _clean(customer_name):
        qs = qs.filter(search_q(_clean(customer_name), "customer__name"))
    if _clean(customer_code):
        qs = qs.filter(search_q(_clean(customer_code), "customer__code"))
    if _clean(payment_status):
        qs = qs.filter(payment_status=_clean(payment_status))
    if _clean(date_from):
        start = _day_start(_clean(date_from))
        qs = qs.filter(created_at__gte=start) if start else qs.filter(created_at__date__gte=_clean(date_from))
    if _clean(date_to):
        end = _next_day_start(_clean(date_to))
        qs = qs.filter(created_at__lt=end) if end else qs.filter(created_at__date__lte=_clean(date_to))
    if _clean(min_outstanding):
        qs = qs.filter(credit_outstanding__gte=_clean(min_outstanding))
    if _clean(max_outstanding):
        qs = qs.filter(credit_outstanding__lte=_clean(max_outstanding))

    return qs.order_by("-credit_outstanding")