# Does Gross Profit Double-Count Tax? — Reference Note

> **Question this answers:** "We calculate gross profit as selling price − (COGS + taxes), but we also pay GST/WHT separately — do we need to adjust the formula to stop double-counting tax?"
>
> **Verdict (2026-07-29): No adjustment needed.** The current formula is not what the question assumes (taxes aren't simply subtracted once) — it's a two-stage pass-through that nets to zero once tax is actually remitted. See the worked example below. Re-read this note before changing anything in `billing/utils.py`, `purchases/utils.py`, or the tax-deduction lines in `profits/services.py` — it explains why they're shaped the way they are.

---

## 1. What's actually implemented (not "selling price − (COGS + taxes)")

```
gross_profit (per invoice) = grand_total − COGS

grand_total = subtotal + GST_collected_from_customer − WHT_withheld_by_customer
COGS        = gross_purchase_price + GST_paid_to_supplier − WHT_withheld_from_supplier   (FIFO-blended)
```

Then, independently, **Monthly Profit** (`profits/services.py`) subtracts two more things when they actually happen:

```
net_profit = ... − gst_paid − wht_paid + ...
```

- `gst_paid` = net GST actually remitted to FBR (`TaxPayment`, tracks `TaxFlow.net_sales_tax_payable = output_tax_collected − input_tax_paid`).
- `wht_paid` = WHT actually deposited to FBR — **but only the supplier-side withholding**. WHT withheld *by your customers* is never paid by this business at all (see `taxes/models.py`, `WHTPayment` docstring: "WHT withheld by customers is never paid by this business, so it has no payment ledger").

**Source of truth for each piece:**

| Piece | File |
|---|---|
| Invoice-level `line_gst`/`line_wht`/`line_total` formula | `billing/utils.py::calculate_line_item` |
| `gross_profit = grand_total − total_cogs` | `billing/utils.py::calculate_invoice_totals` |
| Purchase-level `gst_amount`/`wht_amount`/`total_price` (FIFO cost basis) | `purchases/utils.py::calculate_total_price` |
| `gst_paid` / `wht_paid` deductions in Monthly Profit | `profits/services.py::_compute_gst_paid`, `_compute_wht_paid` |
| Customer-side vs supplier-side WHT distinction | `taxes/models.py` — `TaxFlow` docstring, `WHTPayment` docstring |
| Real cash movement when tax is remitted | `cash_flow/services.py::sync_tax_payment_made`, `sync_wht_payment_made` |

---

## 2. Why it isn't double-counting — worked example

Buy 10 units @ Rs. 100, GST 18%, WHT 1% (withheld from supplier):

```
gross            = 1000
gst_paid_to_supplier = 180
wht_from_supplier    = 10
net_payable (to supplier) = 1000 + 180 − 10 = 1170
COGS per unit (FIFO)      = 1170 / 10 = 117
```

Sell all 10 units @ Rs. 150, GST 18%, WHT 1% (withheld by customer):

```
line_gross       = 1500
gst_collected    = 270
wht_by_customer  = 15
grand_total      = 1500 + 270 − 15 = 1755

gross_profit = grand_total − COGS = 1755 − 1170 = 585
```

**Now remit the tax** (assume same month, no carryover — the realistic case has a lag, see §3):

```
gst_paid (net FBR remittance) = output_tax − input_tax = 270 − 180 = 90
wht_paid (supplier-side deposit)                        = 10

net_profit = gross_profit − gst_paid − wht_paid = 585 − 90 − 10 = 485
```

**Cross-check against real cash movement** (the only way to know if the number is "true"):

```
+ 1755   cash actually received from customer (net of the WHT they withheld — you never touch that 15)
− 1170   cash actually paid to supplier
−   10   cash remitted to FBR (WHT withheld from supplier)
−   90   cash remitted to FBR (net GST)
= 485    cash actually retained
```

`485 == 485`. The formula is exact, not a coincidence — GST collected inflates revenue and GST paid-to-supplier deflates COGS, so `gst_paid` (the net of those two) always exactly zeroes out the pass-through when remitted. Same mechanism for supplier-side WHT: COGS already excludes it (that cash never went to the supplier), and `wht_paid` re-adds it as a cost the moment it's actually deposited.

---

## 3. The one real effect: timing lag (by design, not a bug)

If GST/WHT collected in June isn't remitted until July:

- **June** shows `gross_profit = 585`, no `gst_paid`/`wht_paid` yet → June's `net_profit` is **overstated by 100** (the not-yet-remitted tax).
- **July** shows `gst_paid = 90`, `wht_paid = 10`, with no matching revenue that month → July's `net_profit` absorbs the full **-100** hit.
- Combined across both months: `585 − 100 = 485` — still exactly right, just shifted in time.

This is consistent with the project's established philosophy elsewhere: recognize a cash event in the month it *actually happens*, not the month it was earned/incurred (same reasoning behind the Lost/Found Inventory dated-recovery fix — see `profits/profit_calculation_breakdown.md` §6). **Don't "fix" this lag by trying to accrue tax in the sale's month** — that would break the cash-based recognition convention every other deduction in `MonthlyProfit` follows.

---

## 4. When this note would actually need revisiting

Only if one of these becomes true — otherwise leave the formula alone:

- **GST registration status changes** (e.g., business becomes unregistered / flat-rate) — `input_tax_paid` credit against `output_tax_collected` may no longer apply the same way.
- **WHT withheld by customers starts being paid by this business** (e.g., a change in FBR filing responsibility) — would require a payment ledger for `total_wht_withheld_by_customers`, mirrored on the customer side of `WHTPayment`.
- **Remittance cadence becomes highly irregular** (e.g., tax paid annually instead of ~monthly) — the timing lag in §3 would stretch across many months, which is still mathematically correct but may look confusing on the Monthly Profit page; could warrant a "tax payable but not yet remitted" info line (display-only, not a formula change).
- **A real example is found where cash-in-hand and net_profit disagree** for a fully-settled period (no outstanding tax) — that would mean the formula itself is wrong, not just lagged. Verify with the same worked-example method as §2 before changing any code.

See also: `backend/profits/profit_calculation_breakdown.md` for the full Monthly Profit formula (expenses, lost/found inventory, depreciation, disposal gain/loss) — this note only covers the tax-inside-revenue/COGS piece.








<!-- I traced this through the actual code rather than going from the formula as you described it, since what's implemented isn't quite "selling price − (COGS + taxes)":

Currently: gross_profit = grand_total − COGS, where grand_total = subtotal + GST_collected − WHT_withheld_by_customer, and COGS (FIFO cost) = gross + GST_paid_to_supplier − WHT_withheld_from_supplier per purchase batch. Then separately, Monthly Profit subtracts gst_paid (net GST actually remitted to FBR) and wht_paid (WHT actually deposited, but only the supplier-side withholding — WHT withheld by your customers is never paid by you, per WHTPayment's own docstring).

Does this double-count? I worked through the arithmetic and it doesn't — it's a pass-through: GST collected inflates revenue, GST paid-to-suppliers deflates COGS, and gst_paid (the net FBR remittance) brings the combined effect back to zero once actually paid. Same logic for supplier-side WHT: it's subtracted out of COGS at purchase time (since that portion goes to FBR, not the supplier), then wht_paid re-adds it as a real cost exactly when it's actually remitted — together they equal the true full cost. The only real effect is a timing lag (tax collected/embedded this month, remitted next month) — which is consistent with how you already wanted Lost/Found Inventory to work (recognize when cash actually moves), not a bug.

My recommendation: leave the formula as-is — I don't think it needs adjusting. Is there a specific number that looked wrong to you, or a different real-world tax mechanic (e.g., GST not remitted monthly, or WHT working differently for your FBR filing) that's not matching what I described above? -->