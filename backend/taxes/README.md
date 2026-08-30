# Taxes — How This Works

This document explains, in plain terms, how the system tracks the store's
sales tax and withholding tax position. It's written so an accountant can
read it and understand exactly what each number means and where it comes
from — and so the store owner (a developer, not an accountant) can follow
the reasoning too.

**Important disclaimer up front:** the store is not currently registered
with FBR for Sales Tax. Everything in this module is an internal estimate/
management tool built on the real Sales Tax Act, 1990 mechanics, using tax
figures already recorded on every purchase and sale. It is **not** a
substitute for a qualified tax consultant or accountant, and should be
reviewed against actual FBR filings before being relied on for anything
official.

---

## 1. The two taxes this system tracks, and why they're kept separate

Pakistani law actually has two completely different taxes hiding under one
word ("tax" on your invoices), and this module deliberately keeps them
apart because mixing them would produce a number that doesn't mean anything
to FBR:

### Sales Tax (GST) — the tax that can be netted

This is the tax you see as "GST" on purchase and sale documents (currently
18% standard rate on most goods, though stationery items were moved to a
reduced rate under the Finance Act 2024 — rates change almost every year,
which is why this system never hardcodes a rate; you enter the actual GST%
on each purchase/invoice line, same as before this feature existed).

**The core rule (Sales Tax Act, 1990, Section 7):** a sales-tax-registered
business does not simply hand over every rupee of GST it charges customers.
It's allowed to subtract the GST it already paid to its own suppliers
first, and only pay FBR the **difference**. This is exactly what the store
owner asked this module to calculate:

```
Net Sales Tax Payable = Output Tax (charged to customers)
                       − Input Tax (paid to suppliers)
```

- If this number is **positive**, the store technically owes FBR that
  amount for the period.
- If this number is **negative** (which is what this store's real data
  currently shows — see "Current position" below), the store has paid more
  GST to its suppliers than it has collected from customers. Under FBR
  rules, excess input tax is either refunded (for exporters/zero-rated
  sales) or carried forward to offset future periods — it is never treated
  as an amount the store owes.

### Withholding Tax (WHT) — a completely different regime, not netted

WHT (Income Tax Ordinance, 2001, Section 153) is **not** sales tax. It's an
advance payment against annual income tax, and it flows in one direction
per transaction, not two sides of the same ledger:

- **WHT withheld from suppliers**: when the store (as the buyer) pays a
  supplier, it may be required to deduct WHT from that payment and deposit
  it with FBR on the supplier's behalf. This is real cash the store has
  already deducted and is holding — a genuine liability to FBR. **This side
  is now payment-tracked** (see "WHT Payments" below).
- **WHT withheld by customers**: when a customer pays the store, *they* may
  deduct WHT from what they owe and deposit it with FBR directly, on the
  store's behalf. The store never touches this money. It's not income the
  store lost — it's a **credit** the store can claim against its own annual
  income tax return. **This side has no payment ledger and never will** —
  the store never holds this cash, so there's nothing for it to pay.

These two numbers cannot be netted against each other, and neither can be
netted against Sales Tax — they belong to a different tax law entirely. In
concrete terms: WHT deducted from Supplier A's payment must be deposited on
Supplier A's tax account; a WHT credit sitting on the store's own account
(deposited there by Customer B) cannot be used to cover that obligation,
because it's a different taxpayer's money on a different taxpayer's account.
That's why the "amount to pay" for WHT (`wht_outstanding`) is built only
from the supplier side — a running total minus payments made, not a
difference of two flows like Sales Tax.

---

## 2. Decisions made for this version, and why

These were discussed and agreed with the store owner before anything was
built. Listed here so an accountant reviewing this module — or a future
developer extending it — knows which choices were deliberate trade-offs,
not gaps someone forgot about.

| Decision | Why |
|---|---|
| **GST and WHT are never netted together** | They're legally different tax regimes (Sales Tax Act vs Income Tax Ordinance). A combined number would not correspond to anything FBR recognizes, so keeping them apart is the only version that's actually correct. |
| **Built as an internal tool, not a live FBR filing system** | The store is not currently registered for Sales Tax. Every figure here is a management estimate for the owner's own visibility, not a submission to FBR. |
| **v1 shows the raw, uncapped Net Sales Tax Payable** | FBR's Section 8B caps how much input tax can be claimed per period (90% of output tax) with carry-forward for the rest. Implementing that properly requires period-by-period tracking, which is a meaningfully bigger feature. Ship the core numbers first, verify they're correct, then add the cap — rather than adding complexity before the basics are trusted. |
| **Figures use a flexible date range for reporting, not FBR's fixed monthly cycle** | Matches how every other report in this system already works. Since the store isn't filing monthly returns yet, there was no reason to force a monthly structure on this feature specifically. |
| **WHT withheld from suppliers is now payment-tracked; WHT withheld by customers stays read-only, permanently** | WHT withheld by customers is money the store never touches (the customer deposits it with FBR directly) — there is nothing for the store to "pay" on that side, ever. WHT withheld from suppliers is a real liability the store is holding, so it now has its own "WHT Payments" ledger (`total_wht_paid` / `wht_outstanding`), mirroring the existing Tax Payments ledger for GST — same reasoning, same shape. |
| **Running all-time balances, not period-tied payments** | Mirrors how supplier payables already work elsewhere in this system: a gross "total ever paid" figure plus a net "still outstanding" figure, both stored fields kept up to date automatically. Simpler, consistent with the rest of the app, and sufficient since there's no monthly filing deadline driving this yet. |
| **Frontend exists for Sales Tax and WHT Payments, no dashboard card yet** | The Taxes page and Tax/WHT Payments list/create/delete flows are built. A dashboard summary card was intentionally left out so far — see item 5 below. |
| **Every total is calculated off data the system already had** (`gst_total`/`wht_total` already stored on every purchase order and invoice) | No new tax math was introduced — this module aggregates numbers that were already being calculated and stored for purchase/invoice documents. Lower risk than re-deriving tax figures from scratch. |

---

## 3. What each field on the Tax Flow record actually means

The system keeps one live record (like a running balance sheet) that
updates itself automatically every time a purchase or sale is confirmed —
nothing here is calculated on the fly when you open the page; it's kept
up to date in the background so it stays fast no matter how much history
builds up.

| Field | Accountant meaning | Updates when... |
|---|---|---|
| **Input Tax Paid** | Total GST paid to suppliers, all-time | A purchase order is confirmed |
| **Output Tax Collected** | Total GST charged to customers, all-time | An invoice is confirmed |
| **Net Sales Tax Payable** | Output − Input. What you'd owe FBR today if registered and filing right now | Recalculated every time either total above changes |
| **Sales Tax Paid** | Total GST actually paid to FBR, all-time | A "Tax Payment" is recorded |
| **Sales Tax Outstanding** | Net Payable − Sales Tax Paid, never shown below zero | Recalculated every time either total above changes |
| **WHT Withheld from Suppliers** | Tax deducted from supplier payments — a real liability to FBR | A purchase order is confirmed |
| **WHT Withheld by Customers** | Tax customers deducted from what they paid you — a credit for your annual return, informational only, no payment tracking | An invoice is confirmed |
| **WHT Paid** | Total WHT actually deposited to FBR against tax withheld from suppliers, all-time | A "WHT Payment" is recorded |
| **WHT Outstanding** | WHT Withheld from Suppliers − WHT Paid, never shown below zero. Never netted against WHT Withheld by Customers — different taxpayer's obligation | Recalculated every time either total above changes |

Two separate ledgers record actual FBR deposits:
- **Tax Payments** — real GST payments made to FBR.
- **WHT Payments** — real WHT deposits made to FBR, against tax withheld
  from suppliers only (there is no equivalent ledger for tax withheld by
  customers — the store never holds that cash).

Recording either immediately reduces Cash in Hand on the main dashboard,
exactly the same way recording an Expense does — it's real money leaving
the till.

---

## 4. Current position (as of the last backfill)

```
Input Tax Paid (to suppliers)     : Rs 1,002,348.00
Output Tax Collected (from customers): Rs    11,241.00
Net Sales Tax Payable             : Rs  -991,107.00   (you're in an excess-credit position, not owing)
Sales Tax Outstanding             : Rs         0.00
WHT Withheld from Suppliers       : Rs    55,686.00   (real FBR liability)
WHT Withheld by Customers         : Rs       624.22   (informational credit only)
WHT Paid                          : Rs         0.00   (no WHT deposits recorded yet)
WHT Outstanding                   : Rs    55,686.00
```

**Why Output Tax is so much smaller than Input Tax:** this almost certainly
means most of the store's confirmed invoices currently have 0% GST entered
on them, while most purchases do carry GST. Worth double-checking with
whoever enters invoice line items — if customers genuinely aren't being
charged GST (e.g. informal retail sales), this is expected and correct.
If GST should be on more invoices and simply isn't being entered, that's a
data-entry gap, not a bug in this module.

---

## 5. What's intentionally missing in v1 (and why)

This module was built deliberately narrow for a first version. Nothing
below is an oversight — each is a documented decision, made with the store
owner, and can be added later without reworking what's already here:

1. **Returns don't reduce these totals.** If a purchase or a sale is later
   returned, the GST/WHT already recorded against it stays on the books.
   This matches how every other running total in this system already works
   (lost inventory, purchase/customer returns, revenue) — nothing was
   singled out to behave differently. If your accountant needs returns
   reflected, that's a defined follow-up, not a redesign.

2. **No 90%-of-output-tax cap (Section 8B).** FBR limits how much input tax
   can be claimed in a single period to 90% of that period's output tax,
   carrying the rest forward. v1 shows the raw, uncapped difference so the
   core numbers can be verified as correct first — the 90% rule adds
   period-by-period carry-forward tracking, which is meaningfully more
   complex and is planned as a v2 addition once this foundation is trusted.

3. **No payment tracking for WHT withheld by customers** — and there never
   will be. The store never holds that cash, so there's nothing to record a
   payment against. (WHT withheld from suppliers *does* have payment
   tracking — see "WHT Payments" above.)

4. **No period grouping.** Figures are all-time running totals, not broken
   down by FBR's monthly filing calendar. Since the store isn't currently
   registered/filing, this wasn't needed yet.

5. **No dashboard summary card yet.** The Taxes page exists as its own
   section, but none of these figures are surfaced on the main dashboard
   the way CashFlow/AssetFlow stats are.

6. **Input tax assumes every supplier is GST-registered.** Legally, input
   tax is only claimable on purchases from suppliers who are themselves
   sales-tax-registered and issue a valid tax invoice. This system doesn't
   currently track supplier registration status, so every GST amount
   recorded on a purchase is treated as claimable. If some suppliers are
   unregistered, the true claimable input tax is lower than what's shown
   here.

---

## 6. Future plans (in rough priority order, not committed dates)

1. Add supplier GST-registration status, so Input Tax Paid can split into
   "claimable" vs "not legally creditable."
2. Add the Section 8B 90%-cap + carry-forward logic once the store
   registers with FBR (or earlier, if useful for planning ahead).
3. Add return-reversal logic for GST/WHT totals, matching whatever
   convention gets adopted for the rest of the system's running totals.
4. Add a monthly tax-period view once the store is registered and needs to
   match its actual filing calendar.

---

## 7. Recommendations (things worth discussing with an accountant)

These are practical suggestions, not implemented features — flagging them
because they affect whether the numbers in this module mean what you think
they mean:

1. **Get this module's output reviewed by a real accountant or tax
   consultant before relying on it for anything beyond internal
   visibility.** It's built on genuine FBR mechanics, but it is not a
   substitute for professional review, especially before registering or
   filing anything officially.

2. **Investigate why Output Tax Collected is so much smaller than Input Tax
   Paid** (see "Current position" above). Either most sales genuinely carry
   no GST (fine, just confirm it's intentional), or GST is being under-
   entered on invoices (a data-entry fix, not a code fix). This is the
   single most important thing to check before trusting these numbers.

3. **Consider whether the store is close to a mandatory Sales Tax
   registration threshold.** Certain business types (wholesalers, Tier-1
   retailers, importers) must register with FBR regardless of turnover.
   Worth confirming current status with an accountant rather than assuming
   registration is optional indefinitely.

4. **Track which suppliers are GST-registered**, since only tax invoices
   from registered suppliers produce legally claimable input tax. Right
   now this module assumes all recorded GST is claimable — worth
   validating that assumption against your actual supplier list.

5. **Decide, with your accountant, how returns should affect these
   totals** before this becomes a live filing tool — the "only ever
   increases" convention used everywhere else in this system may not be
   the right call specifically for tax figures once returns become
   material.

---

## 8. API reference (for developers)

All endpoints require an authenticated admin or superuser (`is_staff=True`
or superuser) — normal users get a 403.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/taxes/stats/` | Current tax position (all 9 fields above) |
| GET | `/api/taxes/payments/` | List GST payments (filters: `search`, `date_from`, `date_to`, `min_amount`, `max_amount`) |
| POST | `/api/taxes/payments/` | Record a new GST payment to FBR — deducts Cash in Hand |
| GET | `/api/taxes/payments/<id>/` | Retrieve a single GST payment |
| DELETE | `/api/taxes/payments/<id>/` | Soft-delete a GST payment — restores Cash in Hand |
| GET | `/api/taxes/wht-payments/` | List WHT payments (same filters as above) |
| POST | `/api/taxes/wht-payments/` | Record a new WHT deposit to FBR (against tax withheld from suppliers) — deducts Cash in Hand |
| GET | `/api/taxes/wht-payments/<id>/` | Retrieve a single WHT payment |
| DELETE | `/api/taxes/wht-payments/<id>/` | Soft-delete a WHT payment — restores Cash in Hand |

Run `python manage.py backfill_taxflow` any time to recompute the Tax Flow
singleton from scratch off existing confirmed purchases/invoices/payments —
safe to re-run, always lands on the correct absolute value.
