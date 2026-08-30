# How to Change Tax Values Directly in the Database — Safely

> **Context:** Sometimes you need to change `TaxFlow`'s numbers directly (reset, correct a mistake, start fresh) **without** touching Invoices or PurchaseOrders. This is a direct database intervention, outside the app's normal user-facing flow — done wrong, it silently corrupts `cash_in_hand`, leaves orphaned payment records, or gets overwritten the next time `backfill_taxflow` runs. This note is the exact, verified procedure. It was written after actually performing a full tax reset on the real production database (2026-07-29) — every step below was run and its output checked, not just theorized.

---

## 0. Understand what you're touching before you touch it

| Piece | What it is | Where it's defined |
|---|---|---|
| `TaxFlow` | Singleton (one row, `pk=1`) — the live dashboard/report numbers: GST input/output/payable/paid/outstanding, WHT withheld-from-suppliers/by-customers/paid/outstanding | `taxes/models.py` |
| `TaxPayment` | Ledger — one row per real GST payment made to FBR. Soft-deletable. | `taxes/models.py` |
| `WHTPayment` | Ledger — one row per real WHT deposit made to FBR (**supplier-side only** — WHT withheld by customers has no payment ledger, see model docstring) | `taxes/models.py` |
| `_adjust_taxflow()` | **The ONLY function allowed to write to `TaxFlow`.** Delta-based, recomputes the two derived fields (`net_sales_tax_payable`, `sales_tax_outstanding`, `wht_outstanding`) every call. | `taxes/services.py` |
| `delete_tax_payment()` / `delete_wht_payment()` | Soft-deletes a payment, restores its amount to `CashFlow.cash_in_hand`, and reduces the matching `TaxFlow` field via `_adjust_taxflow()` | `taxes/services.py` |

**Two raw `TaxFlow` fields are synced from Invoice/PurchaseOrder data that this procedure does NOT touch:**
- `total_input_tax_paid` / `total_wht_withheld_from_suppliers` ← confirmed `PurchaseOrder.gst_total`/`wht_total`
- `total_output_tax_collected` / `total_wht_withheld_by_customers` ← confirmed `Invoice.gst_total`/`wht_total`

**This means:** if you zero these fields without touching the underlying Invoices/PurchaseOrders, and someone later re-runs `python manage.py backfill_taxflow`, it will recompute `TaxFlow` straight back from those still-intact source records — your change will silently disappear. This is expected, not a bug — flag it to whoever asked for the change, don't try to "fix" it by editing invoices/orders (that's a much bigger, much riskier change and almost certainly not what was actually wanted).

---

## 1. Golden rules (apply to both methods below)

1. **Never assign `TaxFlow` fields directly** (`tf.total_input_tax_paid = 0; tf.save()`). Always go through `_adjust_taxflow(..., user=user)` with a **delta**, even for a full reset (`delta = -current_value`). This keeps the two derived fields correct and `last_updated_by`/`last_updated_at` honest.
2. **Never hard-delete `TaxPayment`/`WHTPayment` rows.** Always go through `delete_tax_payment()`/`delete_wht_payment()` — soft-delete (`is_deleted=True`) preserves the audit trail and is the only path that also restores `cash_in_hand` correctly.
3. **Wrap the whole change in one `transaction.atomic()` block.** If anything raises partway through, the whole thing rolls back — no half-applied state.
4. **Print before/after values and verify the arithmetic**, especially the `cash_in_hand` delta — it must equal the exact sum of whatever `TaxPayment`/`WHTPayment` amounts you deleted. If it doesn't match, stop and investigate before trusting the result.
5. **Confirm you did NOT touch Invoice/PurchaseOrder records** — spot-check `Invoice.objects.filter(status='confirmed').aggregate(Sum('gst_total'), Sum('wht_total'))` and the `PurchaseOrder` equivalent before and after; they must be identical.
6. **Run through `python manage.py shell`**, not raw SQL — this ensures Django signals/model `save()` logic (e.g. `AuditMixin` timestamps) still fire correctly.
7. **Delete any temporary script file** you wrote for this once you're done — don't leave one-off DB-mutation scripts lying around the repo.
8. This is real, irreversible production data. **Offer a full local backup first** (the app has a built-in Backups feature — `POST /api/backups/full/local/`) unless the user explicitly declines.

---

## Method A — No payment records involved ("without payment")

Use this when you just want to change `TaxFlow`'s raw synced numbers (e.g. a full reset, or correcting one field) and there are **no `TaxPayment`/`WHTPayment` rows to worry about** — either none exist yet, or you've deliberately decided to leave existing payment records alone.

```python
from django.db import transaction
from taxes.models import TaxFlow
from taxes.services import _adjust_taxflow
from users.models import User

user = User.objects.first()  # or the specific acting user

with transaction.atomic():
    tf = TaxFlow.get_instance()
    print("BEFORE:", tf.total_input_tax_paid, tf.total_output_tax_collected,
          tf.total_wht_withheld_from_suppliers, tf.total_wht_withheld_by_customers)

    _adjust_taxflow(
        total_input_tax_paid_delta              = -tf.total_input_tax_paid,               # or any target delta
        total_output_tax_collected_delta        = -tf.total_output_tax_collected,
        total_wht_withheld_from_suppliers_delta = -tf.total_wht_withheld_from_suppliers,
        total_wht_withheld_by_customers_delta   = -tf.total_wht_withheld_by_customers,
        user=user,
    )

tf.refresh_from_db()
print("AFTER:", tf.total_input_tax_paid, tf.total_output_tax_collected,
      tf.net_sales_tax_payable, tf.sales_tax_outstanding,
      tf.total_wht_withheld_from_suppliers, tf.total_wht_withheld_by_customers, tf.wht_outstanding)
```

`total_sales_tax_paid`/`total_wht_paid` deltas are omitted here on purpose — with no payment records, they should already be whatever they are (likely already correct/zero); only pass a delta for them if you specifically know they need to change and have confirmed no `TaxPayment`/`WHTPayment` rows back them.

---

## Method B — Payment records also need clearing ("with payment")

Use this when real `TaxPayment`/`WHTPayment` rows exist and the change also requires removing (or adjusting) them — e.g. a full reset where payment history should go too. **Order matters**: clear the payments first (this naturally reduces `total_sales_tax_paid`/`total_wht_paid` and restores `cash_in_hand`), *then* adjust the remaining raw fields.

```python
from django.db import transaction
from taxes.models import TaxFlow, TaxPayment, WHTPayment
from taxes.services import delete_tax_payment, delete_wht_payment, _adjust_taxflow
from cash_flow.models import CashFlow
from users.models import User

user = User.objects.first()

cf_before = CashFlow.get_instance()
print("cash_in_hand BEFORE:", cf_before.cash_in_hand)

with transaction.atomic():
    # Step 1 — soft-delete every payment that needs clearing (or filter to specific pks)
    for p in list(TaxPayment.objects.filter(is_deleted=False)):
        print("deleting TaxPayment", p.id, p.amount)
        delete_tax_payment(pk=p.id, user=user)

    for p in list(WHTPayment.objects.filter(is_deleted=False)):
        print("deleting WHTPayment", p.id, p.amount)
        delete_wht_payment(pk=p.id, user=user)

    # Step 2 — now clear the remaining raw fields that payments don't touch
    tf = TaxFlow.get_instance()
    _adjust_taxflow(
        total_input_tax_paid_delta              = -tf.total_input_tax_paid,
        total_output_tax_collected_delta        = -tf.total_output_tax_collected,
        total_wht_withheld_from_suppliers_delta = -tf.total_wht_withheld_from_suppliers,
        total_wht_withheld_by_customers_delta   = -tf.total_wht_withheld_by_customers,
        user=user,
    )

tf.refresh_from_db()
cf_after = CashFlow.get_instance()

print("TaxFlow FINAL:", {f.name: getattr(tf, f.name) for f in TaxFlow._meta.fields
                          if f.name not in ("id", "last_updated_at", "last_updated_by")})
print("cash_in_hand AFTER:", cf_after.cash_in_hand)
print("cash_in_hand delta:", cf_after.cash_in_hand - cf_before.cash_in_hand,
      "  <- must equal the exact sum of deleted TaxPayment + WHTPayment amounts")
print("active TaxPayment left:", TaxPayment.objects.filter(is_deleted=False).count())
print("active WHTPayment left:", WHTPayment.objects.filter(is_deleted=False).count())
```

If only *some* payments should be cleared (not all), filter the two `for` loops to specific `pk`s instead of `is_deleted=False` on the whole table.

---

## 2. Final verification (run after either method)

```python
from billing.models import Invoice
from purchases.models import PurchaseOrder
from django.db.models import Sum

inv = Invoice.objects.filter(is_deleted=False, status="confirmed").aggregate(gst=Sum("gst_total"), wht=Sum("wht_total"))
po  = PurchaseOrder.objects.filter(is_deleted=False, status="confirmed").aggregate(gst=Sum("gst_total"), wht=Sum("wht_total"))
print("Invoice totals (must be unchanged from before):", inv)
print("PurchaseOrder totals (must be unchanged from before):", po)
```

Compare these two lines against the values you captured **before** making any change. If either differs, something touched Invoice/PurchaseOrder records — stop and investigate; that was not supposed to happen under either method.

---

## 3. Prompt for another AI

Paste the block below as-is (fill in the `<...>` placeholders) to have another AI agent execute this correctly against this codebase.

```
You are working in the AlphaPK Django ERP backend. I need you to change TaxFlow
values directly in the database, following the exact procedure documented in
backend/taxes/how_to_change_tax_values.md — read that file first and follow it
precisely. Do not deviate from it or invent your own approach.

Task: <describe exactly what to change, e.g. "reset all TaxFlow fields to zero"
or "reduce total_output_tax_collected by 50,000" — be specific about which
fields and target values/deltas>.

Payment records: <state whether TaxPayment/WHTPayment rows exist and need
clearing too — "yes, clear all of them" / "yes, clear only payment id X" /
"no, leave existing payment records alone">.

Requirements (non-negotiable):
1. Use Method A (no payment records) or Method B (with payment records) from
   the md file above, matching what I specified.
2. NEVER assign TaxFlow fields directly — only via taxes.services._adjust_taxflow(),
   passing deltas, with a real `user` argument.
3. NEVER hard-delete TaxPayment/WHTPayment — only via
   taxes.services.delete_tax_payment() / delete_wht_payment().
4. Wrap everything in one transaction.atomic() block.
5. Do NOT modify any Invoice or PurchaseOrder record, under any circumstance.
6. Print before/after values for every TaxFlow field and for CashFlow.cash_in_hand,
   and confirm the cash_in_hand delta exactly equals the sum of any deleted
   payment amounts.
7. After the change, run the "Final verification" query from the md file and
   confirm Invoice/PurchaseOrder GST/WHT aggregate totals are IDENTICAL to
   before the change.
8. If anything printed doesn't match what's expected, stop, report the
   mismatch, and do not proceed further.
9. Delete any temporary script file you created for this once done.
10. Report back: what changed, the exact before/after numbers, and explicit
    confirmation that Invoices/PurchaseOrders were not touched.

Run this through `python manage.py shell`, not raw SQL. This is real production
data — be precise, verify every number, and do not guess.
```
