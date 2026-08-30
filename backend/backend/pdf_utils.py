import base64
from functools import lru_cache
from pathlib import Path

from django.conf import settings

# ---------------------------------------------------------------------------
# Global PDF spacing — every PDF template (invoice, purchase order, ledger,
# report) reads these two via context instead of hardcoding its own numbers,
# so page spacing can be tuned in one place for all documents at once.
#
# PDF_PAGE_MARGIN: WeasyPrint's @page { margin: ... } — this is what actually
# controls the page's outer whitespace, NOT body padding (a template with no
# @page rule still gets WeasyPrint's own ~2cm default). Reference points for
# A4:
#   small  = "10mm"  — tightest layout, most content per page
#   medium = "15mm"  — balanced, standard document margin (what report_pdf.html
#                       already used before this was centralized)
#   normal = "20mm"  — traditional/generous margin (e.g. Word's default)
PDF_PAGE_MARGIN = "15mm"

# PDF_BODY_PADDING: extra inner spacing INSIDE the @page margin above. Usually
# "0" is correct — the @page margin already provides the outer gap; only
# raise this for additional breathing room between the page edge and content.
#   small  = "0mm"
#   medium = "4mm"
#   normal = "8mm"
PDF_BODY_PADDING = "0mm"


@lru_cache(maxsize=1)
def get_company_logo_data_uri() -> str:
    """
    Embeds the logo as a base64 data URI so WeasyPrint doesn't need to
    resolve a filesystem/URL path (which differs between dev and prod) —
    works identically everywhere the file is present on disk.
    Cached: the logo file doesn't change without a redeploy.
    """
    logo_path = Path(settings.STATIC_ROOT) / "images" / "logo.png"
    if not logo_path.is_file():
        return ""
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
