import os
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from backend.pdf_utils import PDF_BODY_PADDING, PDF_PAGE_MARGIN, get_company_logo_data_uri

from .models import PurchaseOrder, SavedPurchaseOrderPDF
from .selectors import get_purchase_order_by_id


def _get_pdf_dir(year: int) -> Path:
    path = Path(settings.MEDIA_ROOT) / "purchase_orders" / str(year)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _build_item_context(order: PurchaseOrder) -> list[dict]:
    items = []
    # .all() hits the selector's prefetch cache (live items only via
    # SoftDeleteManager) instead of re-querying per item.
    for item in order.items.all():
        items.append({
            "product_name" : item.product.name,
            "product_code" : item.product.code,
            "quantity"     : item.quantity,
            "unit_price"   : item.unit_price,
            "gst"          : item.gst,
            "wht"          : item.wht,
            "gross_amount" : item.gross_amount,
            "gst_amount"   : item.gst_amount,
            "wht_amount"   : item.wht_amount,
            "total_price"  : item.total_price,
            "description"  : item.description,
        })
    return items


def _render_order_html(order: PurchaseOrder, is_draft: bool = False) -> str:
    # localtime() converts the UTC-stored value to settings.TIME_ZONE before
    # formatting — strftime() on the raw aware datetime would print the UTC day.
    order_date = (
        timezone.localtime(order.confirmed_at).strftime("%d %b %Y")
        if order.confirmed_at
        else timezone.localtime(order.created_at).strftime("%d %b %Y")
    )
    context = {
        "order"       : order,
        "items"       : _build_item_context(order),
        "order_date"  : order_date,
        "is_draft"    : is_draft,
        "generated_at": timezone.localtime(timezone.now()).strftime("%d %b %Y %H:%M"),
        "company_name": settings.COMPANY_NAME,
        "company_logo": get_company_logo_data_uri(),
        "page_margin" : PDF_PAGE_MARGIN,
        "body_padding": PDF_BODY_PADDING,
    }
    return render_to_string("purchases/purchase_order_pdf.html", context)


def _html_to_pdf_bytes(html: str) -> bytes:
    from weasyprint import HTML
    return HTML(string=html, base_url=str(settings.MEDIA_ROOT)).write_pdf()


def generate_purchase_order_pdf_bytes(*, order_id: int, is_draft: bool = False) -> tuple[bytes, str]:
    """
    Streams PDF — nothing saved to disk.
    Draft orders can be printed with a DRAFT watermark; confirmed orders print clean.
    """
    order    = get_purchase_order_by_id(order_id)
    html     = _render_order_html(order, is_draft=is_draft)
    pdf      = _html_to_pdf_bytes(html)
    filename = f"{order.order_number}{'_DRAFT' if is_draft else ''}.pdf"
    return pdf, filename


def save_purchase_order_pdf(*, order_id: int, file_name: str, user) -> SavedPurchaseOrderPDF:
    """
    Generates and saves PDF to disk. Only confirmed orders.
    File: media/purchase_orders/<year>/<file_name>_<timestamp>.pdf
    """
    from rest_framework.exceptions import ValidationError
    order = get_purchase_order_by_id(order_id)
    if order.status == PurchaseOrder.Status.DRAFT:
        raise ValidationError({"order": "Only confirmed purchase orders can be saved as PDF."})

    html      = _render_order_html(order)
    pdf       = _html_to_pdf_bytes(html)
    local_now = timezone.localtime(timezone.now())
    year      = local_now.year
    timestamp = local_now.strftime("%Y%m%d_%H%M%S")
    safe_name = file_name.strip().replace(" ", "_").replace("/", "-")
    filename  = f"{safe_name}_{timestamp}.pdf"
    pdf_dir   = _get_pdf_dir(year)
    full_path = pdf_dir / filename

    with open(full_path, "wb") as f:
        f.write(pdf)

    # Forward slashes (as_posix) so the stored path is URL-safe on every OS.
    relative_path = (Path("purchase_orders") / str(year) / filename).as_posix()
    return SavedPurchaseOrderPDF.objects.create(
        order=order, file_name=file_name.strip(),
        file_path=relative_path, saved_by=user,
    )


def delete_purchase_order_pdf(*, saved_pdf_id: int, user) -> None:
    from django.shortcuts import get_object_or_404
    record    = get_object_or_404(SavedPurchaseOrderPDF, pk=saved_pdf_id, is_deleted=False)
    full_path = Path(settings.MEDIA_ROOT) / record.file_path
    if full_path.exists():
        os.remove(full_path)
    record.is_deleted = True
    record.deleted_at = timezone.now()
    record.deleted_by = user
    record.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


def get_saved_pdfs_for_order(order_id: int):
    return SavedPurchaseOrderPDF.objects.filter(
        order_id=order_id, is_deleted=False,
    ).select_related("saved_by").order_by("-created_at")