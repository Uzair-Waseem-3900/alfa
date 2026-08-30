from datetime import date as date_cls
from decimal import Decimal
from itertools import accumulate

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import (
    CustomerLedger, CustomerLedgerEntry, CustomerLedgerSnapshot,
    SavedCustomerLedgerPDF, SavedLedgerPDF,
    SupplierLedger, SupplierLedgerEntry, SupplierLedgerSnapshot,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_year_month(date) -> str:
    """Returns 'YYYY-MM' string from a date or datetime."""
    return date.strftime("%Y-%m")


def _as_date(value):
    """
    Normalizes a YYYY-MM-DD query-param string to a date (dates/None pass
    through; unparseable strings become None → filter skipped). The view
    layer hands strings straight to the balance code, which previously
    crashed on .strftime for any string date_from.
    """
    if value is None or isinstance(value, date_cls):
        return value
    return parse_date(str(value))


def _month_bounds(year_month: str) -> tuple:
    """
    (first day of month, first day of NEXT month) for a 'YYYY-MM' string —
    lets month filters be real date ranges that use the (ledger, date)
    index, instead of date__startswith, which casts the date column to text
    for a LIKE and forces a sequential scan.
    """
    year, month = map(int, year_month.split("-"))
    start = date_cls(year, month, 1)
    end = date_cls(year + 1, 1, 1) if month == 12 else date_cls(year, month + 1, 1)
    return start, end


def _get_previous_snapshot_balance_generic(snapshot_model, ledger, year_month: str) -> Decimal:
    """
    Model-agnostic core: returns the closing balance of the most recent
    snapshot BEFORE year_month for the given snapshot model/ledger.
    Returns 0 if no prior snapshot exists (opening balance = 0).
    """
    snapshot = (
        snapshot_model.objects
        .filter(ledger=ledger, year_month__lt=year_month)
        .order_by("-year_month")
        .first()
    )
    return snapshot.closing_balance if snapshot else Decimal("0")


def _recalculate_snapshots_from_generic(
    entry_model, snapshot_model, ledger, from_year_month: str,
    debit_increases: bool = False,
) -> None:
    """
    Model-agnostic core: recalculates all monthly snapshots from
    from_year_month onwards. Called when any entry in a month is created,
    edited, or deleted.

    For each affected month:
      closing_balance = prior_snapshot_balance + sum(credits) - sum(debits)  (supplier: debit_increases=False)
      closing_balance = prior_snapshot_balance + sum(debits) - sum(credits)  (customer: debit_increases=True)
    """
    from django.db.models import Sum

    # Get all months that need recalculation (from_year_month onwards)
    affected_months = (
        snapshot_model.objects
        .filter(ledger=ledger, year_month__gte=from_year_month)
        .order_by("year_month")
        .values_list("year_month", flat=True)
    )

    # Also include from_year_month itself even if no snapshot exists yet
    months_to_process = sorted(set(list(affected_months) + [from_year_month]))

    for ym in months_to_process:
        prior_balance = _get_previous_snapshot_balance_generic(snapshot_model, ledger, ym)

        # Sum all entries in this month — real date range so the
        # (ledger, date) index is used (date__startswith could not use it).
        month_start, month_end = _month_bounds(ym)
        agg = entry_model.objects.filter(
            ledger=ledger,
            date__gte=month_start,
            date__lt=month_end,
        ).aggregate(
            total_credit=Sum("credit"),
            total_debit=Sum("debit"),
        )
        month_credit = agg["total_credit"] or Decimal("0")
        month_debit  = agg["total_debit"]  or Decimal("0")

        delta = (month_debit - month_credit) if debit_increases else (month_credit - month_debit)
        closing_balance = prior_balance + delta
        # Store real balance including negative (overpaid/overdue state)
        snapshot_model.objects.update_or_create(
            ledger=ledger,
            year_month=ym,
            defaults={"closing_balance": closing_balance},
        )


def _recalculate_snapshots_from(ledger: SupplierLedger, from_year_month: str) -> None:
    _recalculate_snapshots_from_generic(SupplierLedgerEntry, SupplierLedgerSnapshot, ledger, from_year_month)


def _recalculate_customer_snapshots_from(ledger: "CustomerLedger", from_year_month: str) -> None:
    _recalculate_snapshots_from_generic(
        CustomerLedgerEntry, CustomerLedgerSnapshot, ledger, from_year_month, debit_increases=True,
    )


# ---------------------------------------------------------------------------
# Ledger creation (called when supplier is created)
# ---------------------------------------------------------------------------

def delete_ledger(*, pk: int, user) -> None:
    """
    Soft-deletes a SupplierLedger. Only allowed once the linked supplier is
    itself soft-deleted — a ledger must never disappear out from under a
    still-active supplier.
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    ledger = get_object_or_404(
        SupplierLedger.objects.select_related("supplier"), pk=pk, is_deleted=False,
    )
    if not ledger.supplier.is_deleted:
        raise ValidationError({
            "detail": "Cannot delete ledger: the supplier must be deleted first.",
        })

    ledger.is_deleted = True
    ledger.deleted_at = timezone.now()
    ledger.deleted_by = user
    ledger.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


def create_ledger_for_supplier(*, supplier) -> SupplierLedger:
    """
    Auto-creates an empty SupplierLedger when a supplier is created.
    Snapshots supplier name/code for historical preservation.
    """
    return SupplierLedger.objects.get_or_create(
        supplier=supplier,
        defaults={
            "supplier_name": supplier.name,
            "supplier_code": supplier.code,
        },
    )[0]


def sync_ledger_snapshot(*, supplier) -> None:
    """
    Keeps the ledger's name/code snapshot tracking the live supplier while
    it's still active. Called by purchases.services.update_supplier every
    time the supplier is renamed/re-coded. The snapshot only stays frozen
    once the supplier itself is soft-deleted (nothing calls this after that).
    """
    SupplierLedger.objects.filter(supplier=supplier).exclude(
        supplier_name=supplier.name, supplier_code=supplier.code,
    ).update(supplier_name=supplier.name, supplier_code=supplier.code)


def delete_customer_ledger(*, pk: int, user) -> None:
    """
    Soft-deletes a CustomerLedger. Only allowed once the linked customer is
    itself soft-deleted — a ledger must never disappear out from under a
    still-active customer.
    """
    from django.shortcuts import get_object_or_404
    from rest_framework.exceptions import ValidationError

    ledger = get_object_or_404(
        CustomerLedger.objects.select_related("customer"), pk=pk, is_deleted=False,
    )
    if not ledger.customer.is_deleted:
        raise ValidationError({
            "detail": "Cannot delete ledger: the customer must be deleted first.",
        })

    ledger.is_deleted = True
    ledger.deleted_at = timezone.now()
    ledger.deleted_by = user
    ledger.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


def create_ledger_for_customer(*, customer) -> CustomerLedger:
    """
    Auto-creates an empty CustomerLedger when a customer is created.
    Snapshots customer name/code for historical preservation.
    """
    return CustomerLedger.objects.get_or_create(
        customer=customer,
        defaults={
            "customer_name": customer.name,
            "customer_code": customer.code,
        },
    )[0]


def sync_customer_ledger_snapshot(*, customer) -> None:
    """
    Keeps the ledger's name/code snapshot tracking the live customer while
    it's still active. Called by billing.services.update_customer every
    time the customer is renamed/re-coded. Mirrors sync_ledger_snapshot.
    """
    CustomerLedger.objects.filter(customer=customer).exclude(
        customer_name=customer.name, customer_code=customer.code,
    ).update(customer_name=customer.name, customer_code=customer.code)


def _get_locked_customer_ledger(customer) -> CustomerLedger:
    """
    Self-healing lookup used by every customer entry-write function below.
    A CustomerLedger normally already exists (auto-created alongside the
    customer by create_customer()) — but a customer created through any
    OTHER path (Django admin's CustomerAdmin has no save_model override;
    import_customer_data.py creates Customer rows directly) would otherwise
    crash every one of these writes with CustomerLedger.DoesNotExist the
    first time that customer has any sale/payment/advance/return. get_or_create
    is idempotent under a race (real OneToOne constraint on customer), same
    safety net create_ledger_for_customer already provides for the normal path.
    """
    CustomerLedger.objects.get_or_create(
        customer=customer,
        defaults={"customer_name": customer.name, "customer_code": customer.code},
    )
    return CustomerLedger.objects.select_for_update().get(customer=customer)


# ---------------------------------------------------------------------------
# Entry creation — called from purchases.services
# ---------------------------------------------------------------------------

@transaction.atomic
def add_purchase_entry(
    *, supplier, purchase_order, amount: Decimal, date, user,
) -> SupplierLedgerEntry:
    """Purchase confirmed → Credit entry (we owe supplier more)."""
    # Lock the ledger row: two entries for the same supplier written
    # concurrently would each recalculate the month snapshot without seeing
    # the other's uncommitted entry — last writer would store a balance
    # missing one entry. The lock serializes writes per supplier only.
    ledger = SupplierLedger.objects.select_for_update().get(supplier=supplier)
    entry  = SupplierLedgerEntry.objects.create(
        ledger          = ledger,
        entry_type      = SupplierLedgerEntry.EntryType.PURCHASE,
        date            = date,
        details         = f"Purchase Order: {purchase_order.description or purchase_order.order_number}",
        reference       = purchase_order.order_number,
        credit          = amount,
        debit           = Decimal("0"),
        purchase_order  = purchase_order,
        created_by      = user,
    )
    _recalculate_snapshots_from(ledger, _get_year_month(date))
    return entry


@transaction.atomic
def add_opening_balance_entry(
    *, supplier, amount: Decimal, date, reference: str,
    details: str = "Opening Balance", user,
) -> SupplierLedgerEntry:
    """
    Data-entry bootstrap: one-time opening balance for a supplier.
    Credit entry (we owe supplier from before go-live).
    """
    # Lock the ledger row: two entries for the same supplier written
    # concurrently would each recalculate the month snapshot without seeing
    # the other's uncommitted entry — last writer would store a balance
    # missing one entry. The lock serializes writes per supplier only.
    ledger = SupplierLedger.objects.select_for_update().get(supplier=supplier)
    entry  = SupplierLedgerEntry.objects.create(
        ledger     = ledger,
        entry_type = SupplierLedgerEntry.EntryType.OPENING_BALANCE,
        date       = date,
        details    = details,
        reference  = reference,
        credit     = amount,
        debit      = Decimal("0"),
        created_by = user,
    )
    _recalculate_snapshots_from(ledger, _get_year_month(date))
    return entry


@transaction.atomic
def add_payment_entry(
    *, supplier, supplier_payment, amount: Decimal, date, user,
) -> SupplierLedgerEntry:
    """Supplier payment made → Debit entry (we paid them)."""
    # Lock the ledger row: two entries for the same supplier written
    # concurrently would each recalculate the month snapshot without seeing
    # the other's uncommitted entry — last writer would store a balance
    # missing one entry. The lock serializes writes per supplier only.
    ledger = SupplierLedger.objects.select_for_update().get(supplier=supplier)
    entry  = SupplierLedgerEntry.objects.create(
        ledger           = ledger,
        entry_type       = SupplierLedgerEntry.EntryType.PAYMENT,
        date             = date,
        details          = supplier_payment.note or "Supplier payment",
        reference        = supplier_payment.reference_number,
        debit            = amount,
        credit           = Decimal("0"),
        supplier_payment = supplier_payment,
        created_by       = user,
    )
    _recalculate_snapshots_from(ledger, _get_year_month(date))
    return entry


@transaction.atomic
def add_advance_entry(
    *, supplier, supplier_payment, amount: Decimal, date, user,
) -> SupplierLedgerEntry:
    """Advance payment on draft PO → Debit entry."""
    # Lock the ledger row: two entries for the same supplier written
    # concurrently would each recalculate the month snapshot without seeing
    # the other's uncommitted entry — last writer would store a balance
    # missing one entry. The lock serializes writes per supplier only.
    ledger = SupplierLedger.objects.select_for_update().get(supplier=supplier)
    entry  = SupplierLedgerEntry.objects.create(
        ledger           = ledger,
        entry_type       = SupplierLedgerEntry.EntryType.ADVANCE,
        date             = date,
        details          = supplier_payment.note or "Advance payment",
        reference        = supplier_payment.reference_number,
        debit            = amount,
        credit           = Decimal("0"),
        supplier_payment = supplier_payment,
        created_by       = user,
    )
    _recalculate_snapshots_from(ledger, _get_year_month(date))
    return entry


@transaction.atomic
def add_return_entry(
    *, supplier, purchase_return, amount: Decimal, date, user,
) -> SupplierLedgerEntry:
    """Purchase return accepted → Debit entry (supplier owes us back)."""
    # Lock the ledger row: two entries for the same supplier written
    # concurrently would each recalculate the month snapshot without seeing
    # the other's uncommitted entry — last writer would store a balance
    # missing one entry. The lock serializes writes per supplier only.
    ledger = SupplierLedger.objects.select_for_update().get(supplier=supplier)
    entry  = SupplierLedgerEntry.objects.create(
        ledger          = ledger,
        entry_type      = SupplierLedgerEntry.EntryType.RETURN,
        date            = date,
        details         = purchase_return.note or f"Return against {purchase_return.order.order_number}",
        reference       = purchase_return.reference_number,
        debit           = amount,
        credit          = Decimal("0"),
        purchase_return = purchase_return,
        created_by      = user,
    )
    _recalculate_snapshots_from(ledger, _get_year_month(date))
    return entry


# ---------------------------------------------------------------------------
# Entry deletion — reverses an existing ledger entry
# ---------------------------------------------------------------------------

@transaction.atomic
def remove_ledger_entry_for_payment(*, supplier_payment) -> None:
    """
    Removes ledger entry linked to a supplier payment (deleted payment).
    Cascades snapshot recalculation from the affected month.
    """
    entry = SupplierLedgerEntry.objects.filter(supplier_payment=supplier_payment).first()
    if not entry:
        return
    # Same per-supplier write lock as the add-entry services.
    ledger    = SupplierLedger.objects.select_for_update().get(pk=entry.ledger_id)
    from_ym   = _get_year_month(entry.date)
    entry.delete()
    _recalculate_snapshots_from(ledger, from_ym)


@transaction.atomic
def remove_ledger_entry_for_return(*, purchase_return) -> None:
    """Removes ledger entry linked to a purchase return (if return is reversed)."""
    entry = SupplierLedgerEntry.objects.filter(purchase_return=purchase_return).first()
    if not entry:
        return
    # Same per-supplier write lock as the add-entry services.
    ledger  = SupplierLedger.objects.select_for_update().get(pk=entry.ledger_id)
    from_ym = _get_year_month(entry.date)
    entry.delete()
    _recalculate_snapshots_from(ledger, from_ym)


# ---------------------------------------------------------------------------
# Customer ledger entries — called from billing.services / data_entry.services
#
# Direction is flipped from the supplier side: Debit = customer owes us
# more (sale/opening balance), Credit = customer owes us less
# (payment/advance/return).
# ---------------------------------------------------------------------------

@transaction.atomic
def add_sale_entry(
    *, customer, invoice, amount: Decimal, date, user,
) -> CustomerLedgerEntry:
    """Invoice confirmed → Debit entry (customer owes us more)."""
    # Lock the ledger row: two entries for the same customer written
    # concurrently would each recalculate the month snapshot without seeing
    # the other's uncommitted entry — last writer would store a balance
    # missing one entry. The lock serializes writes per customer only.
    ledger = _get_locked_customer_ledger(customer)
    entry  = CustomerLedgerEntry.objects.create(
        ledger      = ledger,
        entry_type  = CustomerLedgerEntry.EntryType.SALE,
        date        = date,
        details     = f"Invoice: {invoice.bill_number}",
        reference   = invoice.bill_number,
        debit       = amount,
        credit      = Decimal("0"),
        invoice     = invoice,
        created_by  = user,
    )
    _recalculate_customer_snapshots_from(ledger, _get_year_month(date))
    return entry


@transaction.atomic
def add_customer_opening_balance_entry(
    *, customer, invoice, amount: Decimal, date, reference: str,
    details: str = "Opening Balance", user,
) -> CustomerLedgerEntry:
    """
    Data-entry bootstrap: one-time opening balance for a customer.
    Debit entry (they owed us from before go-live).
    """
    ledger = _get_locked_customer_ledger(customer)
    entry  = CustomerLedgerEntry.objects.create(
        ledger      = ledger,
        entry_type  = CustomerLedgerEntry.EntryType.OPENING_BALANCE,
        date        = date,
        details     = details,
        reference   = reference,
        debit       = amount,
        credit      = Decimal("0"),
        invoice     = invoice,
        created_by  = user,
    )
    _recalculate_customer_snapshots_from(ledger, _get_year_month(date))
    return entry


@transaction.atomic
def add_customer_payment_entry(
    *, customer, payment, amount: Decimal, date, user,
) -> CustomerLedgerEntry:
    """Payment received → Credit entry (customer owes us less)."""
    ledger = _get_locked_customer_ledger(customer)
    entry  = CustomerLedgerEntry.objects.create(
        ledger      = ledger,
        entry_type  = CustomerLedgerEntry.EntryType.PAYMENT,
        date        = date,
        details     = payment.note or "Customer payment",
        reference   = payment.reference_number,
        credit      = amount,
        debit       = Decimal("0"),
        payment     = payment,
        created_by  = user,
    )
    _recalculate_customer_snapshots_from(ledger, _get_year_month(date))
    return entry


@transaction.atomic
def add_customer_advance_entry(
    *, customer, payment, amount: Decimal, date, user,
) -> CustomerLedgerEntry:
    """Advance payment on draft invoice → Credit entry (paid upfront)."""
    ledger = _get_locked_customer_ledger(customer)
    entry  = CustomerLedgerEntry.objects.create(
        ledger      = ledger,
        entry_type  = CustomerLedgerEntry.EntryType.ADVANCE,
        date        = date,
        details     = payment.note or "Advance payment",
        reference   = payment.reference_number,
        credit      = amount,
        debit       = Decimal("0"),
        payment     = payment,
        created_by  = user,
    )
    _recalculate_customer_snapshots_from(ledger, _get_year_month(date))
    return entry


@transaction.atomic
def add_customer_return_entry(
    *, customer, customer_return, amount: Decimal, date, user,
) -> CustomerLedgerEntry:
    """Return accepted → Credit entry (reduces what the customer owes)."""
    ledger = _get_locked_customer_ledger(customer)
    entry  = CustomerLedgerEntry.objects.create(
        ledger          = ledger,
        entry_type      = CustomerLedgerEntry.EntryType.RETURN,
        date            = date,
        details         = customer_return.note or f"Return against {customer_return.invoice.bill_number}",
        reference       = customer_return.reference_number,
        credit          = amount,
        debit           = Decimal("0"),
        customer_return = customer_return,
        created_by      = user,
    )
    _recalculate_customer_snapshots_from(ledger, _get_year_month(date))
    return entry


# ---------------------------------------------------------------------------
# Customer entry deletion — reverses an existing ledger entry
# ---------------------------------------------------------------------------

@transaction.atomic
def remove_customer_ledger_entry_for_payment(*, payment) -> None:
    """
    Removes ledger entry linked to a billing payment (deleted payment).
    A no-op for payments that never got an entry (e.g. the negative
    credit-note payment auto-created by accept_return, which is tracked
    via its own Return-linked entry instead).
    """
    entry = CustomerLedgerEntry.objects.filter(payment=payment).first()
    if not entry:
        return
    ledger  = CustomerLedger.objects.select_for_update().get(pk=entry.ledger_id)
    from_ym = _get_year_month(entry.date)
    entry.delete()
    _recalculate_customer_snapshots_from(ledger, from_ym)


@transaction.atomic
def remove_customer_ledger_entry_for_return(*, customer_return) -> None:
    """Removes ledger entry linked to a customer return (if return is reversed)."""
    entry = CustomerLedgerEntry.objects.filter(customer_return=customer_return).first()
    if not entry:
        return
    ledger  = CustomerLedger.objects.select_for_update().get(pk=entry.ledger_id)
    from_ym = _get_year_month(entry.date)
    entry.delete()
    _recalculate_customer_snapshots_from(ledger, from_ym)


# ---------------------------------------------------------------------------
# PDF services
# ---------------------------------------------------------------------------

def save_ledger_pdf(
    *, ledger_id: int, file_name: str, date_from=None, date_to=None, user,
) -> SavedLedgerPDF:
    from pathlib import Path
    from django.conf import settings as django_settings
    from django.shortcuts import get_object_or_404

    ledger = get_object_or_404(SupplierLedger, pk=ledger_id)
    pdf, _ = generate_ledger_pdf_bytes(
        ledger_id=ledger_id, date_from=date_from, date_to=date_to,
    )

    local_now = timezone.localtime(timezone.now())
    year      = local_now.year
    timestamp = local_now.strftime("%Y%m%d_%H%M%S")
    safe_name = file_name.strip().replace(" ", "_").replace("/", "-")
    filename  = f"{safe_name}_{timestamp}.pdf"
    pdf_dir   = Path(django_settings.MEDIA_ROOT) / "ledgers" / str(year)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    full_path = pdf_dir / filename

    with open(full_path, "wb") as f:
        f.write(pdf)

    # Forward slashes (as_posix) so the stored path is URL-safe on every OS.
    relative_path = (Path("ledgers") / str(year) / filename).as_posix()
    return SavedLedgerPDF.objects.create(
        ledger=ledger,
        file_name=file_name.strip(),
        file_path=relative_path,
        date_from=date_from,
        date_to=date_to,
        saved_by=user,
    )


def delete_ledger_pdf(*, saved_pdf_id: int, user) -> None:
    import os
    from pathlib import Path
    from django.conf import settings as django_settings
    from django.shortcuts import get_object_or_404

    record    = get_object_or_404(SavedLedgerPDF, pk=saved_pdf_id, is_deleted=False)
    full_path = Path(django_settings.MEDIA_ROOT) / record.file_path
    if full_path.exists():
        os.remove(full_path)

    record.is_deleted = True
    record.deleted_at = timezone.now()
    record.deleted_by = user
    record.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


def generate_ledger_pdf_bytes(
    *, ledger_id: int, date_from=None, date_to=None,
) -> tuple[bytes, str]:
    from django.conf import settings as django_settings
    from django.template.loader import render_to_string
    from django.shortcuts import get_object_or_404

    from backend.pdf_utils import PDF_BODY_PADDING, PDF_PAGE_MARGIN, get_company_logo_data_uri

    ledger  = get_object_or_404(SupplierLedger, pk=ledger_id)
    entries, opening_balance, closing_balance = _get_entries_with_running_balance(
        ledger=ledger, date_from=date_from, date_to=date_to,
    )

    # Treat opening-balance entries as the account's Opening Balance figure shown
    # in the header, rather than as a transaction row. Their effect is already
    # baked into every subsequent running balance, so the remaining rows stay
    # correct. `opening_balance` is the carried-forward balance for date ranges;
    # add any opening_balance entries that fall inside the shown window.
    ob_from_entries = sum(
        (e["credit"] - e["debit"]) for e in entries if e["entry_type"] == "opening_balance"
    )
    header_opening_balance = opening_balance + ob_from_entries
    display_entries = [e for e in entries if e["entry_type"] != "opening_balance"]

    context = {
        "ledger"          : ledger,
        "entries"         : display_entries,
        "opening_balance" : header_opening_balance,
        "closing_balance" : closing_balance,
        "date_from"       : date_from,
        "date_to"         : date_to,
        "generated_at"    : timezone.localtime(timezone.now()).strftime("%d %b %Y %H:%M"),
        "currency"        : "PKR",
        "company_name"    : django_settings.COMPANY_NAME,
        "company_logo"    : get_company_logo_data_uri(),
        "page_margin"     : PDF_PAGE_MARGIN,
        "body_padding"    : PDF_BODY_PADDING,
    }
    html     = render_to_string("ledger/supplier_ledger_pdf.html", context)
    from weasyprint import HTML
    pdf      = HTML(string=html, base_url=str(django_settings.MEDIA_ROOT)).write_pdf()
    filename = f"Ledger_{ledger.supplier_code}.pdf"
    return pdf, filename


# ---------------------------------------------------------------------------
# Customer PDF services — mirrors the supplier PDF services above.
# ---------------------------------------------------------------------------

def save_customer_ledger_pdf(
    *, ledger_id: int, file_name: str, date_from=None, date_to=None, user,
) -> SavedCustomerLedgerPDF:
    from pathlib import Path
    from django.conf import settings as django_settings
    from django.shortcuts import get_object_or_404

    ledger = get_object_or_404(CustomerLedger, pk=ledger_id)
    pdf, _ = generate_customer_ledger_pdf_bytes(
        ledger_id=ledger_id, date_from=date_from, date_to=date_to,
    )

    local_now = timezone.localtime(timezone.now())
    year      = local_now.year
    timestamp = local_now.strftime("%Y%m%d_%H%M%S")
    safe_name = file_name.strip().replace(" ", "_").replace("/", "-")
    filename  = f"{safe_name}_{timestamp}.pdf"
    pdf_dir   = Path(django_settings.MEDIA_ROOT) / "customer_ledgers" / str(year)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    full_path = pdf_dir / filename

    with open(full_path, "wb") as f:
        f.write(pdf)

    # Forward slashes (as_posix) so the stored path is URL-safe on every OS.
    relative_path = (Path("customer_ledgers") / str(year) / filename).as_posix()
    return SavedCustomerLedgerPDF.objects.create(
        ledger=ledger,
        file_name=file_name.strip(),
        file_path=relative_path,
        date_from=date_from,
        date_to=date_to,
        saved_by=user,
    )


def delete_customer_ledger_pdf(*, saved_pdf_id: int, user) -> None:
    import os
    from pathlib import Path
    from django.conf import settings as django_settings
    from django.shortcuts import get_object_or_404

    record    = get_object_or_404(SavedCustomerLedgerPDF, pk=saved_pdf_id, is_deleted=False)
    full_path = Path(django_settings.MEDIA_ROOT) / record.file_path
    if full_path.exists():
        os.remove(full_path)

    record.is_deleted = True
    record.deleted_at = timezone.now()
    record.deleted_by = user
    record.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


def generate_customer_ledger_pdf_bytes(
    *, ledger_id: int, date_from=None, date_to=None,
) -> tuple[bytes, str]:
    from django.conf import settings as django_settings
    from django.template.loader import render_to_string
    from django.shortcuts import get_object_or_404

    from backend.pdf_utils import PDF_BODY_PADDING, PDF_PAGE_MARGIN, get_company_logo_data_uri

    ledger  = get_object_or_404(CustomerLedger, pk=ledger_id)
    entries, opening_balance, closing_balance = _get_customer_entries_with_running_balance(
        ledger=ledger, date_from=date_from, date_to=date_to,
    )

    # Treat opening-balance entries as the account's Opening Balance figure shown
    # in the header, rather than as a transaction row — same treatment as the
    # supplier PDF (see generate_ledger_pdf_bytes above).
    ob_from_entries = sum(
        (e["debit"] - e["credit"]) for e in entries if e["entry_type"] == "opening_balance"
    )
    header_opening_balance = opening_balance + ob_from_entries
    display_entries = [e for e in entries if e["entry_type"] != "opening_balance"]

    context = {
        "ledger"          : ledger,
        "entries"         : display_entries,
        "opening_balance" : header_opening_balance,
        "closing_balance" : closing_balance,
        "date_from"       : date_from,
        "date_to"         : date_to,
        "generated_at"    : timezone.localtime(timezone.now()).strftime("%d %b %Y %H:%M"),
        "currency"        : "PKR",
        "company_name"    : django_settings.COMPANY_NAME,
        "company_logo"    : get_company_logo_data_uri(),
        "page_margin"     : PDF_PAGE_MARGIN,
        "body_padding"    : PDF_BODY_PADDING,
    }
    html     = render_to_string("ledger/customer_ledger_pdf.html", context)
    from weasyprint import HTML
    pdf      = HTML(string=html, base_url=str(django_settings.MEDIA_ROOT)).write_pdf()
    filename = f"Ledger_{ledger.customer_code}.pdf"
    return pdf, filename


def _get_entries_with_running_balance_generic(
    *, entry_model, snapshot_model, ledger, date_from=None, date_to=None,
    clamp_opening_balance: bool = False, debit_increases: bool = False,
) -> tuple[list[dict], Decimal, Decimal]:
    """
    Model-agnostic core: returns list of entry dicts with running_balance
    computed using the hybrid method. Hybrid: grab last snapshot before
    date_from (or start), then accumulate current entries.

    debit_increases: which column increases the balance — False (supplier)
    means credit increases it (we owe supplier more), True (customer) means
    debit increases it (they owe us more). Must match the sign convention
    used in _recalculate_snapshots_from_generic, or the snapshot-seeded
    opening balance and the entry-by-entry running balance would disagree.

    clamp_opening_balance: the supplier ledger clamps a negative opening
    balance to 0 (an overpaid supplier balance is the unusual case) BEFORE
    accumulating entries, so every entry's running balance reflects the
    clamped start. The customer ledger legitimately goes negative as often
    as positive (customer overpaid / has credit), so it passes False and
    keeps the real value throughout.
    """
    # Normalize view-layer query-param strings to dates (crash-free and
    # required for the index-friendly range filters below).
    date_from = _as_date(date_from)
    date_to   = _as_date(date_to)

    # Determine opening balance using last snapshot before the query window
    opening_balance = Decimal("0")
    if date_from:
        ym_start = _get_year_month(date_from)
        opening_balance = _get_previous_snapshot_balance_generic(snapshot_model, ledger, ym_start)
        # Add entries from that month before date_from — range filter so the
        # (ledger, date) index is used (date__startswith could not use it).
        from django.db.models import Sum
        month_start, _month_end = _month_bounds(ym_start)
        pre_month_agg = entry_model.objects.filter(
            ledger=ledger,
            date__gte=month_start,
            date__lt=date_from,
        ).aggregate(total_credit=Sum("credit"), total_debit=Sum("debit"))
        pre_month_credit = pre_month_agg["total_credit"] or Decimal("0")
        pre_month_debit  = pre_month_agg["total_debit"]  or Decimal("0")
        opening_balance += (pre_month_debit - pre_month_credit) if debit_increases else (pre_month_credit - pre_month_debit)
        if clamp_opening_balance:
            opening_balance = max(Decimal("0"), opening_balance)

    # Fetch entries in the query window.
    # Order: date ASC, then created_at ASC (exact chronological order of events).
    # Same-day entries appear in the order they were actually created in the system.
    qs = entry_model.objects.filter(ledger=ledger).order_by("date", "created_at")

    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    # Compute running balance — allow negative for display accuracy, so the
    # user can see when they overpaid/overdue.
    result          = []
    running_balance = opening_balance
    for entry in qs:
        delta = (entry.debit - entry.credit) if debit_increases else (entry.credit - entry.debit)
        running_balance = running_balance + delta
        result.append({
            "date"            : entry.date,
            "details"         : entry.details,
            "reference"       : entry.reference,
            "entry_type"      : entry.entry_type,
            "debit"           : entry.debit,
            "credit"          : entry.credit,
            "balance"         : running_balance,
        })

    closing_balance = running_balance
    return result, opening_balance, closing_balance


def _get_entries_with_running_balance(
    *, ledger: SupplierLedger, date_from=None, date_to=None,
) -> tuple[list[dict], Decimal, Decimal]:
    return _get_entries_with_running_balance_generic(
        entry_model=SupplierLedgerEntry, snapshot_model=SupplierLedgerSnapshot,
        ledger=ledger, date_from=date_from, date_to=date_to,
        clamp_opening_balance=True, debit_increases=False,
    )


def _get_customer_entries_with_running_balance(
    *, ledger: CustomerLedger, date_from=None, date_to=None,
) -> tuple[list[dict], Decimal, Decimal]:
    return _get_entries_with_running_balance_generic(
        entry_model=CustomerLedgerEntry, snapshot_model=CustomerLedgerSnapshot,
        ledger=ledger, date_from=date_from, date_to=date_to,
        clamp_opening_balance=False, debit_increases=True,
    )