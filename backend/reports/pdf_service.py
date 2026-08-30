from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone

from backend.pdf_utils import PDF_BODY_PADDING, PDF_PAGE_MARGIN, get_company_logo_data_uri


def _html_to_pdf_bytes(html: str) -> bytes:
    """Converts HTML string to PDF bytes using WeasyPrint — same mechanism as billing/purchases PDFs."""
    from weasyprint import HTML
    return HTML(string=html, base_url=settings.MEDIA_ROOT).write_pdf()


def generate_report_pdf_bytes(
    *, title: str, filter_description: str, columns: list, rows: list, stats: list,
) -> tuple[bytes, str]:
    """
    Generic tabular report PDF — used by every report's print endpoint, so
    there's one template/renderer instead of one per report (the reports are
    all the same shape: a title, a filter description, a stats summary, and
    a table — unlike the invoice/purchase-order PDFs, which are each one
    richly-structured document).

    columns: list of {"key": str, "label": str}
    rows   : list of dicts — already-serialized values, keyed to match columns
    stats  : list of {"label": str, "value": str}
    """
    context = {
        "title"              : title,
        "filter_description" : filter_description,
        "columns"            : columns,
        "rows"               : rows,
        "stats"              : stats,
        "row_count"          : len(rows),
        "generated_at"       : timezone.localtime(timezone.now()).strftime("%d %b %Y %H:%M"),
        "company_name"       : settings.COMPANY_NAME,
        "company_logo"       : get_company_logo_data_uri(),
        "page_margin"        : PDF_PAGE_MARGIN,
        "body_padding"       : PDF_BODY_PADDING,
    }
    html = render_to_string("reports/report_pdf.html", context)
    pdf  = _html_to_pdf_bytes(html)
    safe_title = title.replace(" ", "_").replace("/", "-")
    filename   = f"{safe_title}.pdf"
    return pdf, filename
