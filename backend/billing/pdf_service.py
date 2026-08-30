import os
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from backend.pdf_utils import PDF_BODY_PADDING, PDF_PAGE_MARGIN, get_company_logo_data_uri

from .models import Invoice, SavedInvoicePDF
from .selectors import get_invoice_by_id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_invoice_pdf_dir(year: int) -> Path:
    """Returns and creates the directory for storing invoice PDFs."""
    path = Path(settings.MEDIA_ROOT) / "invoices" / str(year)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_item_context(print_context: dict) -> list[dict]:
    """
    Per-item display context for the PDF template, from the shared
    get_invoice_print_context() (see billing/utils.py — also used by the
    Invoice Preview page's print_preview API field, so the two can never
    disagree on what a draft's numbers actually are).
    """
    return [
        {
            "product_name"           : item["product_name"],
            "product_code"           : item["product_code"],
            "quantity"               : item["quantity"],
            "effective_price_display": f"{item['effective_price']:,.4f}" if item["effective_price"] is not None else "N/A",
            "line_total_display"     : f"{item['line_total']:,.4f}" if item["line_total"] is not None else "N/A",
        }
        for item in print_context["items"]
    ]


def _render_invoice_html(invoice: Invoice, is_draft: bool) -> str:
    """Renders the invoice HTML template with full context."""
    from .utils import get_invoice_print_context

    print_context = get_invoice_print_context(invoice)
    items = _build_item_context(print_context)
    grand_total = print_context["grand_total"]
    grand_total_display = f"{grand_total:,.4f}" if grand_total is not None else "N/A"

    # Resolve invoice date: confirmed_at for confirmed bills, created_at for drafts
    # localtime() converts the UTC-stored value to settings.TIME_ZONE before
    # formatting — strftime() on the raw aware datetime would print the UTC day.
    if invoice.confirmed_at:
        invoice_date = timezone.localtime(invoice.confirmed_at).strftime("%d %b %Y")
    else:
        invoice_date = timezone.localtime(invoice.created_at).strftime("%d %b %Y")

    context = {
        "invoice"            : invoice,
        "items"              : items,
        "is_draft"           : is_draft,
        "grand_total_display": grand_total_display,
        "invoice_date"       : invoice_date,
        "generated_at"       : timezone.localtime(timezone.now()).strftime("%d %b %Y %H:%M"),
        "company_name"       : settings.COMPANY_NAME,
        "company_logo"       : get_company_logo_data_uri(),
        "page_margin"        : PDF_PAGE_MARGIN,
        "body_padding"       : PDF_BODY_PADDING,
    }
    return render_to_string("billing/invoice_pdf.html", context)


def _html_to_pdf_bytes(html: str) -> bytes:
    """Converts HTML string to PDF bytes using WeasyPrint."""
    from weasyprint import HTML
    return HTML(string=html, base_url=settings.MEDIA_ROOT).write_pdf()


# ---------------------------------------------------------------------------
# Public PDF services
# ---------------------------------------------------------------------------

def generate_invoice_pdf_bytes(*, invoice_id: int, is_draft: bool) -> tuple[bytes, str]:
    """
    Generates PDF bytes for streaming (print without saving).
    Returns (pdf_bytes, filename) — nothing written to disk.
    """
    invoice  = get_invoice_by_id(invoice_id)
    html     = _render_invoice_html(invoice, is_draft=is_draft)
    pdf      = _html_to_pdf_bytes(html)
    filename = f"{invoice.bill_number}{'_DRAFT' if is_draft else ''}.pdf"
    return pdf, filename


def save_invoice_pdf(
    *,
    invoice_id : int,
    file_name  : str,
    is_draft   : bool,
    user,
) -> SavedInvoicePDF:
    """
    Generates and saves a PDF to disk under media/invoices/<year>/.
    File name format: <user_supplied_name>_<timestamp>.pdf
    Tracks the saved file in SavedInvoicePDF.
    Only confirmed invoices can be saved. Draft invoices can only be printed.
    """
    from rest_framework.exceptions import ValidationError
    from .models import Invoice

    invoice  = get_invoice_by_id(invoice_id)

    if invoice.status == Invoice.Status.DRAFT:
        raise ValidationError({
            "invoice": (
                "Draft invoices cannot be saved as PDF. "
                "Please confirm the invoice first, or use the print API to print with a DRAFT watermark."
            )
        })

    html     = _render_invoice_html(invoice, is_draft=False)
    pdf      = _html_to_pdf_bytes(html)

    local_now = timezone.localtime(timezone.now())
    year      = local_now.year
    timestamp = local_now.strftime("%Y%m%d_%H%M%S")
    safe_name = file_name.strip().replace(" ", "_").replace("/", "-")
    filename  = f"{safe_name}_{timestamp}.pdf"
    pdf_dir   = _get_invoice_pdf_dir(year)
    full_path = pdf_dir / filename

    with open(full_path, "wb") as f:
        f.write(pdf)

    # Store relative path (relative to MEDIA_ROOT) using forward slashes
    # (as_posix) so it's URL-safe on every OS, including Windows dev machines.
    relative_path = (Path("invoices") / str(year) / filename).as_posix()

    return SavedInvoicePDF.objects.create(
        invoice   = invoice,
        file_name = file_name.strip(),
        file_path = relative_path,
        is_draft  = is_draft,
        saved_by  = user,
    )


def delete_saved_pdf(*, saved_pdf_id: int, user) -> None:
    """
    Soft-deletes the SavedInvoicePDF record and removes the file from disk.
    Tracks who deleted it and when.
    """
    from django.shortcuts import get_object_or_404
    record = get_object_or_404(SavedInvoicePDF, pk=saved_pdf_id, is_deleted=False)

    # Remove file from disk
    full_path = Path(settings.MEDIA_ROOT) / record.file_path
    if full_path.exists():
        os.remove(full_path)

    # Soft delete the record
    record.is_deleted  = True
    record.deleted_at  = timezone.now()
    record.deleted_by  = user
    record.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


def get_saved_pdfs_for_invoice(invoice_id: int):
    """Returns all non-deleted saved PDFs for an invoice."""
    return SavedInvoicePDF.objects.filter(
        invoice_id=invoice_id, is_deleted=False
    ).select_related("saved_by", "deleted_by").order_by("-created_at")