from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from backend.pdf_utils import PDF_BODY_PADDING, PDF_PAGE_MARGIN, get_company_logo_data_uri

from .selectors import get_all_rates


def _build_row_context(rates) -> list[dict]:
    rows = []
    for rate in rates:
        product = rate.product
        rows.append({
            "product_name" : product.name,
            "product_code" : product.code,
            "category_name": product.category.name if product.category else "-",
            "selling_price": rate.selling_price,
        })
    return rows


def _build_filter_description(*, search, category_name, min_price, max_price) -> str:
    parts = []
    if search:
        parts.append(f"Search: {search}")
    if category_name:
        parts.append(f"Category: {category_name}")
    if min_price:
        parts.append(f"Min Price: {min_price}")
    if max_price:
        parts.append(f"Max Price: {max_price}")
    return " | ".join(parts) if parts else "All priced products"


def generate_rate_list_pdf_bytes(
    *, search: str = None, category_id: str = None,
    min_price: str = None, max_price: str = None,
) -> tuple[bytes, str]:
    """
    Streams PDF — nothing saved to disk. Only products that currently have
    a ProductRate row print (get_all_rates queries ProductRate directly, so
    unpriced products are structurally excluded, not filtered out here).
    Applies the exact same filters as the on-screen list.
    """
    rates = get_all_rates(
        search=search, category_id=category_id,
        min_price=min_price, max_price=max_price,
    )

    category_name = None
    if category_id:
        from purchases.models import Category
        cat = Category.objects.filter(pk=category_id).first()
        category_name = cat.name if cat else None

    context = {
        "rows"              : _build_row_context(rates),
        "filter_description": _build_filter_description(
            search=search, category_name=category_name,
            min_price=min_price, max_price=max_price,
        ),
        "generated_at" : timezone.localtime(timezone.now()).strftime("%d %b %Y %H:%M"),
        "company_name" : settings.COMPANY_NAME,
        "company_logo" : get_company_logo_data_uri(),
        "page_margin"  : PDF_PAGE_MARGIN,
        "body_padding" : PDF_BODY_PADDING,
    }
    html = render_to_string("rates/rate_list_pdf.html", context)

    from weasyprint import HTML
    pdf = HTML(string=html, base_url=str(settings.MEDIA_ROOT)).write_pdf()
    filename = f"Product_Rates_{timezone.localdate().strftime('%Y%m%d')}.pdf"
    return pdf, filename
