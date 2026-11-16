"""
Invoice DRAFT writes for the assistant: create / edit / discard.

This is orchestration only. Every business rule (stock, rate list, discount vs.
profit, "only drafts can change") is enforced by the EXISTING billing services
this calls — nothing is re-implemented here. What this layer adds:

  * scope  — drafts only, pay-after-delivery only (no advance: that moves cash
             immediately even on a draft), never confirm, never pay;
  * safety — admin check, a per-user hourly and per-run write budget (re-checked
             under a lock inside the transaction), size limits, finite numbers;
  * audit + idempotency via AgentAction (a retried run that repeats a tool call
    returns what was already done instead of creating a second invoice);
  * unit conversion — a "10%" line discount becomes rupees-per-unit HERE, in
    code, from the product's current rate (the model never does the arithmetic);
  * a readable markdown summary whose numbers come from billing's own
    get_invoice_print_context, with every name escaped (names are untrusted text).
"""
import hashlib
import json
import math
import re
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import ValidationError as DRFValidationError

from billing.models import Invoice
from billing.services import DEFAULT_DUE_DATE_DAYS, create_invoice, delete_invoice, update_invoice_items
from billing.utils import get_invoice_print_context, quantize

from ..exceptions import ToolInputError
from ..models import AgentAction
from ..schemas.invoice import InvoiceDiscountType, InvoiceLineIn
from ..selectors import invoicing as sel

CREATE, UPDATE, DISCARD = "create_draft_invoice", "update_draft_invoice", "discard_draft_invoice"
WRITE_WINDOW = timedelta(hours=1)
TWO_PLACES = Decimal("0.01")


# --------------------------------------------------------------------------- guards

def require_write_access(*, user, run_id, source: str = "chat") -> None:
    """Defence in depth: the chat endpoints are already admin-only, the worker
    re-checks the user, and every write tool checks again. This is the quick
    pre-check; the authoritative budget check happens under a lock (below)."""
    if not (user.is_active and user.is_staff):
        raise ToolInputError("Only admins can create or change invoices.")
    if not run_id:
        raise ToolInputError("Invoices can only be changed while answering a chat message.")
    _check_budget(user, run_id, source)


def _check_budget(user, run_id, source: str = "chat") -> None:
    # chat and bulk have separate hourly budgets (bulk is meant for many invoices at once)
    limit = settings.AGENT_BULK_WRITES_PER_HOUR if source == "bulk" else settings.AGENT_WRITES_PER_HOUR
    if sel.count_writes_since(user, timezone.now() - WRITE_WINDOW, source) >= limit:
        raise ToolInputError(
            f"The hourly limit of {limit} invoice changes has been reached. "
            "Please make further changes in the Billing page, or try again later."
        )
    if source == "bulk":     # one bulk row = one invoice request = one draft
        if sel.count_run_writes(run_id) >= 1:
            raise ToolInputError("This request already created its invoice. One request creates only one invoice.")
    elif sel.count_run_writes(run_id) >= settings.AGENT_WRITES_PER_RUN:
        raise ToolInputError(
            f"At most {settings.AGENT_WRITES_PER_RUN} invoice changes can be made per request. "
            "Ask for the rest in a new message."
        )


def _lock_and_recheck_budget(user, run_id, source: str = "chat") -> None:
    """Call as the FIRST statement inside the write transaction. One model turn can emit many
    parallel tool calls that all pass the unlocked pre-check; locking the user's row makes them
    take turns, and the re-count then sees the earlier ones. (SQLite ignores the lock; Postgres
    honours it.)"""
    get_user_model().objects.select_for_update().get(pk=user.pk)
    _check_budget(user, run_id, source)


def explain(exc: DRFValidationError) -> str:
    """Flatten a DRF ValidationError into one readable sentence for the model."""
    def flat(d):
        if isinstance(d, dict):
            return [m for v in d.values() for m in flat(v)]
        if isinstance(d, (list, tuple)):
            return [m for x in d for m in flat(x)]
        return [str(d)]
    return " ".join(flat(exc.detail)) or "The request was rejected."


def _args_hash(tool: str, payload: dict) -> str:
    raw = json.dumps({"tool": tool, **payload}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


# --------------------------------------------------------------------------- input -> service items

def _load_products(ids) -> dict:
    """All products (with their rate-list row) in ONE query; unknown ids are a plain-language error."""
    ids = list(ids)
    found = sel.load_products(ids)
    for pid in ids:
        if pid not in found:
            raise ToolInputError(f"Product #{pid} was not found. Look it up again with find_product_for_invoice.")
    return found


def _rate(product) -> Decimal:
    try:
        return product.rate.selling_price
    except Exception:
        raise ToolInputError(f"'{product.name}' has no selling price in the rate list, so it can't be invoiced yet.")


def _line_discount(line: InvoiceLineIn, rate: Decimal, product, *, keep: Decimal | None) -> Decimal:
    """Rupees off PER UNIT (that is how billing stores it). A percent is converted
    from the product's CURRENT rate; with neither given the existing value is kept."""
    if line.unit_rate is not None:
        # "qty@rate": the user's own price per unit. Discount = rate list - their rate (negative = surcharge).
        discount = quantize(rate - Decimal(str(line.unit_rate)))
    elif line.discount_percent is not None:
        discount = quantize(rate * Decimal(str(line.discount_percent)) / Decimal("100"))
    elif line.discount_amount is not None:
        discount = quantize(Decimal(str(line.discount_amount)))
    else:
        return keep if keep is not None else Decimal("0")
    if discount > rate:
        raise ToolInputError(
            f"The discount on '{product.name}' (Rs {discount:,.2f} per unit) is more than its price (Rs {rate:,.2f})."
            if line.unit_rate is None else
            f"The rate Rs {line.unit_rate:,.2f} given for '{product.name}' is not a valid price (its list price is Rs {rate:,.2f})."
        )
    if discount < -rate:     # a surcharge may at most double the price
        raise ToolInputError(
            f"The surcharge on '{product.name}' (Rs {-discount:,.2f} per unit) is more than its price (Rs {rate:,.2f})."
            if line.unit_rate is None else
            f"The rate Rs {line.unit_rate:,.2f} given for '{product.name}' is more than double its list price (Rs {rate:,.2f}); "
            "please check the rate."
        )
    return discount


def _rate_notes(lines, products) -> list[str]:
    """One heads-up per line the user priced with qty@rate: say what was stored, so it is never silent."""
    notes = []
    for ln in lines:
        if ln.unit_rate is None:
            continue
        product = products[ln.product_id]
        rate = product.rate.selling_price
        diff = quantize(rate - Decimal(str(ln.unit_rate)))
        what = "no discount" if diff == 0 else (
            f"a discount of Rs {diff:,.2f} per unit" if diff > 0 else f"a surcharge of Rs {-diff:,.2f} per unit")
        notes.append(
            f"you gave a rate of Rs {rate - diff:,.2f} for {_md(product.name)} (rate list Rs {rate:,.2f}), so it is stored as {what}"
        )
    return notes


def _require_looked_up(known, *, customer_id=None, product_ids=()) -> None:
    """Refuse an id the model did not get from find_customer_for_invoice / find_product_for_invoice in this run."""
    if known is None:
        return
    if customer_id is not None and customer_id not in known.customers:
        raise ToolInputError(
            "That customer_id did not come from find_customer_for_invoice in this request, so it may be a different "
            "customer. Call find_customer_for_invoice with the customer name (or code) and use the id it returns. Never guess ids."
        )
    missing = [pid for pid in product_ids if pid not in known.products]
    if missing:
        raise ToolInputError(
            f"Product id(s) {', '.join(str(m) for m in missing)} did not come from find_product_for_invoice in this request. "
            "Call find_product_for_invoice for each product and use the ids it returns. Never guess ids."
        )


def _resets(line: InvoiceLineIn, what: str) -> bool:
    return bool(line.reset) and what in line.reset


def _pct(value: float | None, keep: Decimal | None) -> Decimal:
    """GST/WHT percent, rounded to the 2 decimals billing stores (never silently by the database)."""
    if value is not None:
        return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return keep if keep is not None else Decimal("0")


def _discount_args(invoice_discount: float | None, invoice_discount_type: InvoiceDiscountType):
    """-> (type, value) for billing. No invoice discount given -> (None, None) = leave as is."""
    if invoice_discount is None:
        return None, None
    if not math.isfinite(invoice_discount):
        raise ToolInputError("The invoice discount must be a real number.")
    value = Decimal(str(invoice_discount))
    if value < 0:
        raise ToolInputError("An invoice discount can't be negative.")
    if invoice_discount_type == "percent" and value > 100:
        raise ToolInputError("An invoice discount percentage can't be more than 100.")
    return invoice_discount_type, value


def _due_date(text: str | None):
    if not text:
        return None
    try:
        due = parse_date(text)
    except ValueError:
        due = None
    if due is None:
        raise ToolInputError("The due date must be a real date written as YYYY-MM-DD.")
    if due < timezone.localdate():
        raise ToolInputError("The due date can't be in the past.")
    return due


def _check_line_count(count: int) -> None:
    if count > settings.AGENT_INVOICE_MAX_LINES:
        raise ToolInputError(f"An invoice can have at most {settings.AGENT_INVOICE_MAX_LINES} lines here.")


# --------------------------------------------------------------------------- summary

_MD_SPECIAL = re.compile(r"([\\|\[\]()<>`!*_~])")


def _md(text) -> str:
    """Names are untrusted free text that ends up in a markdown table: collapse line breaks and
    escape everything markdown treats specially, so a crafted name can't break the table,
    plant a link or an image."""
    return _MD_SPECIAL.sub(r"\\\1", re.sub(r"\s+", " ", str(text or "")).strip())


def _money(value) -> str:
    return "N/A" if value is None else f"Rs {Decimal(value):,.2f}"


def _num(value) -> str:
    text = f"{Decimal(value):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def build_summary(invoice, *, defaults: list[str], notes: list[str] | None = None) -> str:
    """Markdown the assistant shows verbatim. Inputs (rate, discount, GST, WHT) come
    from the stored lines; every COMPUTED number comes from billing's own print context."""
    ctx = get_invoice_print_context(invoice)
    items = list(invoice.items.all())
    rows, notes = [], list(notes or [])
    for item, computed in zip(items, ctx["items"]):
        try:
            rate = _money(item.product.rate.selling_price)
        except Exception:
            rate = "N/A"
        rows.append(
            f"| {_md(item.product.name)} ({_md(item.product.code)}) | {item.quantity} | {rate} | "
            f"{_num(item.discount)} | {_num(item.gst)} | {_num(item.wht)} | {_money(computed['line_total'])} |"
        )
        if item.discount < 0:
            notes.append(
                f"the line for {_md(item.product.name)} has a surcharge of Rs {-item.discount:,.2f} per unit "
                "(a negative discount), so it is priced above the rate list"
            )
        if computed["effective_price"] is not None and computed["effective_price"] == 0:
            notes.append(f"the line for {_md(item.product.name)} is free (its discount equals its price)")

    due = invoice.payment_due_date.strftime("%d %b %Y") if invoice.payment_due_date else "not set"
    lines = [
        f"> **DRAFT invoice {invoice.bill_number} — not confirmed.** Stock is not deducted until it is confirmed in the Billing page.",
        "",
        f"**Customer:** {_md(invoice.customer.name)} ({_md(invoice.customer.code)}) · **Due:** {due} · **Payment:** after delivery",
        "",
        "| Product | Qty | Rate | Discount / unit | GST % | WHT % | Line total |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *rows,
        "",
    ]
    if ctx["invoice_discount"]:
        pct = ctx["invoice_discount_percent"]
        label = f"{pct}% " if pct else ""
        lines.append(f"**Invoice discount:** {label}({_money(ctx['invoice_discount'])})")
        lines.append("")
    lines.append(f"**Grand total: {_money(ctx['grand_total'])}**")
    if defaults:
        lines += ["", f"_Defaults used: {', '.join(defaults)}. Tell me if you want any of them changed._"]
    if notes:
        lines += ["", "**Heads-up:** " + "; ".join(n[:1].upper() + n[1:] for n in notes) + "."]
    lines += ["", f"[Open this draft in the app](/billing/invoices/{invoice.id})"]
    return "\n".join(lines)


def _fresh(invoice_id: int):
    from billing.selectors import get_invoice_by_id
    return get_invoice_by_id(invoice_id)


def _result(invoice, *, result: str, defaults: list[str], notes: list[str] | None = None, repeated: bool = False) -> dict:
    return {
        "result": result,
        "already_done_earlier_in_this_request": repeated,
        "bill_number": invoice.bill_number,
        "invoice_id": invoice.id,
        "link": f"/billing/invoices/{invoice.id}",
        "summary_markdown": build_summary(invoice, defaults=defaults, notes=notes),
        "instruction": "Show summary_markdown to the user exactly as given, then say what you assumed or still need.",
    }


def _replay(earlier: AgentAction, *, result: str) -> dict:
    """The same call was already made in this request: return the invoice as it is NOW. If it has
    since been discarded, say so plainly instead of failing."""
    try:
        return _result(_fresh(earlier.invoice_id), result=result, defaults=[], repeated=True)
    except Http404:
        raise ToolInputError(f"{earlier.bill_number} no longer exists as a draft (it was discarded or deleted since).")


def _record(*, user, run_id, chat_id, tool, args_hash, arguments, result, invoice, source="chat"):
    return AgentAction.objects.create(
        user=user, run_id=run_id, chat_id=chat_id, tool=tool, args_hash=args_hash, source=source,
        arguments=arguments, result=result, invoice_id=invoice.id, bill_number=invoice.bill_number,
    )


def _repeat_of(run_id, tool, args_hash):
    return sel.get_action(run_id=run_id, tool=tool, args_hash=args_hash)


# --------------------------------------------------------------------------- CREATE

def create_draft(
    *, user, run_id, chat_id, customer_id: int, lines: list[InvoiceLineIn],
    invoice_discount: float | None, invoice_discount_type: InvoiceDiscountType, due_date: str | None,
    source: str = "chat", known=None,
) -> dict:
    require_write_access(user=user, run_id=run_id, source=source)
    if not lines:
        raise ToolInputError("An invoice needs at least one product line.")
    _check_line_count(len(lines))
    _require_looked_up(known, customer_id=customer_id, product_ids=[ln.product_id for ln in lines])

    due = _due_date(due_date)
    discount_type, discount_value = _discount_args(invoice_discount, invoice_discount_type)
    payload = {
        "customer_id": customer_id, "lines": [ln.model_dump() for ln in lines],
        "invoice_discount": invoice_discount, "invoice_discount_type": invoice_discount_type, "due_date": due_date,
    }
    args_hash = _args_hash(CREATE, payload)
    earlier = _repeat_of(run_id, CREATE, args_hash)
    if earlier:
        return _replay(earlier, result="draft_created")

    products = _load_products(ln.product_id for ln in lines)
    items, seen = [], set()
    for ln in lines:
        if ln.quantity is None:
            raise ToolInputError("Every product line needs a quantity.")
        if ln.product_id in seen:
            raise ToolInputError("The same product appears twice. Combine it into one line.")
        seen.add(ln.product_id)
        product = products[ln.product_id]
        rate = _rate(product)
        items.append({
            "product_id": product.id, "quantity": ln.quantity,
            "discount": _line_discount(ln, rate, product, keep=None),
            "gst": _pct(ln.gst, None), "wht": _pct(ln.wht, None),
        })

    defaults = []
    if any(ln.gst is None for ln in lines):
        defaults.append("GST 0%")
    if any(ln.wht is None for ln in lines):
        defaults.append("WHT 0%")
    if all(ln.discount_percent is None and ln.discount_amount is None and ln.unit_rate is None for ln in lines) \
            and discount_value is None:
        defaults.append("no discount")
    if due is None:
        defaults.append(f"due in {DEFAULT_DUE_DATE_DAYS} days")

    try:
        with transaction.atomic():
            _lock_and_recheck_budget(user, run_id, source)
            invoice = create_invoice(
                customer_id=customer_id, items=items,
                payment_type="after_delivery", advance_amount=Decimal("0"), method_allocations=None,
                payment_due_date=due,
                invoice_discount_type=discount_type or "percent",
                invoice_discount_value=discount_value if discount_value is not None else Decimal("0"),
                user=user,
            )
            _record(user=user, run_id=run_id, chat_id=chat_id, tool=CREATE, args_hash=args_hash,
                    arguments=payload, result=AgentAction.Result.CREATED, invoice=invoice, source=source)
    except IntegrityError:   # a concurrent identical call won; the whole transaction (invoice too) rolled back
        earlier = _repeat_of(run_id, CREATE, args_hash)
        if earlier:
            return _replay(earlier, result="draft_created")
        raise
    except Http404:
        raise ToolInputError("That customer was not found. Look the customer up again with find_customer_for_invoice.")
    except DRFValidationError as exc:
        raise ToolInputError(explain(exc))

    return _result(_fresh(invoice.id), result="draft_created", defaults=defaults, notes=_rate_notes(lines, products))


# --------------------------------------------------------------------------- UPDATE

def update_draft(
    *, user, run_id, chat_id, bill_number: str, set_lines: list[InvoiceLineIn] | None,
    remove_product_ids: list[int] | None, invoice_discount: float | None,
    invoice_discount_type: InvoiceDiscountType, due_date: str | None, clear_invoice_discount: bool = False,
    source: str = "chat", known=None,
) -> dict:
    require_write_access(user=user, run_id=run_id, source=source)
    set_lines, remove_product_ids = set_lines or [], remove_product_ids or []
    if clear_invoice_discount:
        invoice_discount = 0.0           # explicit "remove the invoice discount"; a bare 0 elsewhere means "not given"
    if not (set_lines or remove_product_ids or invoice_discount is not None or due_date):
        raise ToolInputError("Nothing to change. Say what to change: a product line, the invoice discount or the due date.")
    _check_line_count(len(set_lines))              # bounded BEFORE any lookup work
    _check_line_count(len(remove_product_ids))

    due = _due_date(due_date)
    discount_type, discount_value = _discount_args(invoice_discount, invoice_discount_type)
    payload = {
        "bill_number": bill_number.strip(), "set_lines": [ln.model_dump() for ln in set_lines],
        "remove_product_ids": sorted(remove_product_ids), "invoice_discount": invoice_discount,
        "invoice_discount_type": invoice_discount_type, "due_date": due_date, "clear": bool(clear_invoice_discount),
    }
    args_hash = _args_hash(UPDATE, payload)
    earlier = _repeat_of(run_id, UPDATE, args_hash)
    if earlier:
        return _replay(earlier, result="draft_updated")

    try:
        invoice = sel.get_invoice_by_bill(bill_number)
    except Http404:
        raise ToolInputError(f"No invoice with bill number '{bill_number.strip()}' was found.")
    if invoice.status != Invoice.Status.DRAFT:
        raise ToolInputError(
            f"{invoice.bill_number} is already confirmed, so it can't be edited here. "
            "Confirmed invoices are changed from the Billing page."
        )

    # The billing service REPLACES all lines (and with them any shelf choices made on the draft).
    items_now = list(invoice.items.all())
    had_shelf_choices = any(it.shelf_allocations.all() for it in items_now)
    current = {
        it.product_id: {"quantity": it.quantity, "discount": it.discount, "gst": it.gst, "wht": it.wht}
        for it in items_now
    }
    for pid in remove_product_ids:
        if pid not in current:
            raise ToolInputError(f"Product #{pid} is not on {invoice.bill_number}, so it can't be removed.")
        del current[pid]
    # Lines already on this draft are known; a product being ADDED must come from a lookup in this run.
    _require_looked_up(known, product_ids=[ln.product_id for ln in set_lines if ln.product_id not in current])
    products = _load_products(ln.product_id for ln in set_lines)
    for ln in set_lines:
        product = products[ln.product_id]
        rate = _rate(product)
        existing = current.get(ln.product_id)
        if existing is None and ln.quantity is None:
            raise ToolInputError(f"'{product.name}' is a new line, so it needs a quantity.")
        current[ln.product_id] = {
            "quantity": ln.quantity if ln.quantity is not None else existing["quantity"],
            # `reset` is the ONLY way to clear a value: zeros/nulls from the model mean "not given".
            "discount": _line_discount(ln, rate, product, keep=None if _resets(ln, "discount") else (existing["discount"] if existing else None)),
            "gst": _pct(ln.gst, None if _resets(ln, "gst") else (existing["gst"] if existing else None)),
            "wht": _pct(ln.wht, None if _resets(ln, "wht") else (existing["wht"] if existing else None)),
        }
    if not current:
        raise ToolInputError("That would remove every line. To cancel the invoice, discard the draft instead.")
    _check_line_count(len(current))

    items = [{"product_id": pid, **vals} for pid, vals in current.items()]
    try:
        with transaction.atomic():
            _lock_and_recheck_budget(user, run_id, source)
            update_invoice_items(
                invoice_id=invoice.id, items=items,
                payment_type=None, advance_amount=None, method_allocations=None,   # never touch payments
                payment_due_date=due,
                invoice_discount_type=discount_type, invoice_discount_value=discount_value,
                user=user,
            )
            _record(user=user, run_id=run_id, chat_id=chat_id, tool=UPDATE, args_hash=args_hash,
                    arguments=payload, result=AgentAction.Result.UPDATED, invoice=invoice, source=source)
    except IntegrityError:
        earlier = _repeat_of(run_id, UPDATE, args_hash)
        if earlier:
            return _replay(earlier, result="draft_updated")
        raise
    except DRFValidationError as exc:
        raise ToolInputError(explain(exc))

    notes = _rate_notes(set_lines, products)
    if had_shelf_choices:
        notes.append("the shelf choices on this draft were cleared by the edit; set them again in the Billing page before confirming")
    return _result(_fresh(invoice.id), result="draft_updated", defaults=[], notes=notes)


# --------------------------------------------------------------------------- DISCARD

def _discarded(bill: str, *, repeated: bool) -> dict:
    return {
        "result": "discarded", "already_done_earlier_in_this_request": repeated, "bill_number": bill,
        "message": f"{bill} was already discarded." if repeated else f"Draft {bill} was discarded. Its reserved stock is free again.",
    }


def discard_draft(*, user, run_id, chat_id, bill_number: str, source: str = "chat") -> dict:
    require_write_access(user=user, run_id=run_id, source=source)
    payload = {"bill_number": bill_number.strip()}
    args_hash = _args_hash(DISCARD, payload)
    earlier = _repeat_of(run_id, DISCARD, args_hash)
    if earlier:
        return _discarded(earlier.bill_number, repeated=True)

    try:
        invoice = sel.get_invoice_by_bill(bill_number)
    except Http404:
        raise ToolInputError(f"No invoice with bill number '{bill_number.strip()}' was found (it may already be discarded).")
    if invoice.status != Invoice.Status.DRAFT:
        raise ToolInputError(f"{invoice.bill_number} is confirmed and can't be discarded here.")
    if invoice.payment_type == "advance" and invoice.advance_amount > 0:
        raise ToolInputError(
            f"{invoice.bill_number} has an advance payment of {_money(invoice.advance_amount)}; discarding it refunds cash, "
            "so please delete it from the Billing page."
        )

    try:
        with transaction.atomic():
            _lock_and_recheck_budget(user, run_id, source)
            delete_invoice(invoice_id=invoice.id, user=user)
            _record(user=user, run_id=run_id, chat_id=chat_id, tool=DISCARD, args_hash=args_hash,
                    arguments=payload, result=AgentAction.Result.DISCARDED, invoice=invoice, source=source)
    except IntegrityError:
        # Only an identical concurrent discard is acceptable here (its row exists); anything else is a real error.
        earlier = _repeat_of(run_id, DISCARD, args_hash)
        if earlier:
            return _discarded(earlier.bill_number, repeated=True)
        raise
    except DRFValidationError as exc:
        raise ToolInputError(explain(exc))

    return _discarded(invoice.bill_number, repeated=False)


# --------------------------------------------------------------------------- READ (a draft, for review)

def show_draft(*, bill_number: str) -> dict:
    try:
        invoice = sel.get_invoice_by_bill(bill_number)
    except Http404:
        raise ToolInputError(f"No invoice with bill number '{bill_number.strip()}' was found.")
    if invoice.status != Invoice.Status.DRAFT:
        raise ToolInputError(
            f"{invoice.bill_number} is confirmed. For confirmed invoices use find_invoices to see their totals and payments."
        )
    return {"bill_number": invoice.bill_number, "invoice_id": invoice.id,
            "summary_markdown": build_summary(invoice, defaults=[])}


# --------------------------------------------------------------------------- for the runner

def writes_note(run_id) -> str:
    """One sentence naming the invoices this run already changed, for error messages: a run can fail
    AFTER a write, and the user must know the draft exists before retrying."""
    verbs = {"created": "created", "updated": "updated", "discarded": "discarded"}
    done = sel.bills_written_in_run(run_id)
    if not done:
        return ""
    parts = ", ".join(f"{bill} was {verbs.get(result, result)}" for bill, result in done)
    return f" Note: {parts} before this stopped. Check it in the Billing page before asking again."
