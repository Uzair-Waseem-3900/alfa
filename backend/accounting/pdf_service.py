from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from backend.pdf_utils import PDF_BODY_PADDING, PDF_PAGE_MARGIN, get_company_logo_data_uri


def _html_to_pdf_bytes(html: str) -> bytes:
    """Same mechanism as every other PDF in this project (invoices, purchase
    orders, reports/pdf_service.py) — one shared renderer, not reimplemented
    per app."""
    from weasyprint import HTML
    return HTML(string=html, base_url=settings.MEDIA_ROOT).write_pdf()


def generate_statement_pdf_bytes(
    *, title: str, filter_description: str, sections: list, balance_check: dict = None,
) -> tuple[bytes, str]:
    """
    Financial-statement PDF — same header/branding/page-setup as
    reports.pdf_service.generate_report_pdf_bytes (copied verbatim: logo,
    company name, generated-at, filter line, PDF_PAGE_MARGIN/PDF_BODY_PADDING),
    but a sectioned line-item body instead of a flat table, since a
    statement is Revenue/Expenses/Net Income (or Assets/Liabilities/Equity),
    not a list of rows.

    sections: list of {"heading": str, "subtitle": str|None,
        "lines": [{"label": str, "amount": str, "bold": bool}]}
    balance_check: {"is_balanced": bool, "message": str} — Balance Sheet only.
    """
    context = {
        "title"              : title,
        "filter_description" : filter_description,
        "sections"           : sections,
        "balance_check"      : balance_check,
        "generated_at"       : timezone.localtime(timezone.now()).strftime("%d %b %Y %H:%M"),
        "company_name"       : settings.COMPANY_NAME,
        "company_logo"       : get_company_logo_data_uri(),
        "page_margin"        : PDF_PAGE_MARGIN,
        "body_padding"       : PDF_BODY_PADDING,
    }
    html = render_to_string("accounting/statement_pdf.html", context)
    pdf  = _html_to_pdf_bytes(html)
    safe_title = title.replace(" ", "_").replace("/", "-")
    filename   = f"{safe_title}.pdf"
    return pdf, filename
