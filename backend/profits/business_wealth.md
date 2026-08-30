# Business Wealth — How This Works

This document explains, in plain terms, how the system calculates the
store's **total business worth** and how that worth is split between the
owner and every investor. It's written so a non-accountant can follow the
reasoning, and so a future developer extending this module knows exactly
why each number is added or subtracted, not just that it is.

**Important disclaimer up front:** this is an internal management estimate,
not a certified valuation or audited balance sheet. It's built from the same
figures already trusted elsewhere in this system (cash, inventory, assets,
receivables, payables, tax position), combined the way a basic balance
sheet would combine them. It should be reviewed by an accountant before
being relied on for anything beyond internal visibility — especially before
using it to actually distribute profit.

---

## 1. The core idea

**Total Business Worth = everything the business owns, minus everything the
business owes.** This is the standard accounting identity behind every
balance sheet: `Assets − Liabilities = Net Worth (Equity)`. This module
computes exactly that, using numbers this system already tracks and trusts
elsewhere — nothing here is a new kind of calculation, it's an assembly of
existing ones.

Once that total is known, it's split two ways:
- **Investor worth** — what every investor's stake is currently worth.
- **Owner worth** — whatever's left over.

---

## 2. What counts as an asset (added), and why

| Component | Source | Why it's an asset |
|---|---|---|
| **Cash in Hand** | `CashFlow.cash_in_hand` | The most literal asset there is — physical/bank cash actually held right now. |
| **Inventory Value** | Live FIFO cost (same calculation as the Inventory Valuation Report) | Unsold stock is real, sellable value sitting in the store. Valued at what was actually paid for it (FIFO cost), not at retail price — a conservative, defensible number. |
| **Assets' Current Worth** | `AssetFlow.total_current_worth` | Equipment, furniture, fixtures, etc. — valued at their current depreciated/revalued worth, not original cost, so old assets aren't overstated. |
| **Customer Outstanding** | `CashFlow.customer_outstanding` | Money customers owe on unpaid or partially-paid invoices. This is real, collectible value that belongs to the business even though it isn't cash yet — leaving it out would understate worth for any business with outstanding credit sales. |

## 3. What counts as a liability (subtracted), and why

| Component | Source | Why it's a liability |
|---|---|---|
| **Supplier Payable Outstanding** | `CashFlow.supplier_payable_outstanding` | Money the business owes suppliers on unpaid or partially-paid purchase orders. This isn't the business's money to count as worth — it's already spoken for. |
| **Sales Tax (GST) Outstanding** | `TaxFlow.sales_tax_outstanding` | GST collected from customers minus GST already paid to suppliers, minus what's already been deposited to FBR. Whatever's left is money being held on FBR's behalf, not the business's own. |
| **WHT Outstanding** | `TaxFlow.wht_outstanding` | Withholding tax deducted from supplier payments, not yet deposited with FBR. Same reasoning as GST outstanding — it's money the business is holding for someone else (FBR, on the supplier's behalf), not its own. Only the supplier side counts here — WHT withheld *by* customers is never held by the business at all (see `taxes/README.md` for the full explanation), so it was never an asset to begin with and isn't subtracted here either. |
| **Recurring Expense Pending** | `RecurringExpenseFlow.total_pending_amount` | Rent, salaries, utilities, etc. that have been assigned as due for a period but not yet paid. Structurally identical to Supplier Payable Outstanding — an obligation that's already been incurred, just not settled yet. |

## 4. The formula

```
Total Business Worth =
      Cash in Hand
    + Inventory Value
    + Assets' Current Worth
    + Customer Outstanding
    − Supplier Payable Outstanding
    − Sales Tax (GST) Outstanding
    − WHT Outstanding
    − Recurring Expense Pending
```

Every term on the right is read live, at request time, from a number this
system already keeps up to date elsewhere (see "Why this is safe to compute
live" below) — there is no separate stored "business worth" figure that
could drift out of sync with reality.

---

## 5. What was deliberately left out, and why

These aren't oversights — each was considered and excluded on purpose:

1. **WHT withheld by customers** (`TaxFlow.total_wht_withheld_by_customers`).
   The business never holds this cash — the customer deposits it with FBR
   directly, on the business's behalf, as a credit toward its own future
   tax return. It was never an asset sitting anywhere in this system, so
   there's nothing to add or subtract.
2. **Investor capital and owner capital** (`Investor.net_stake`,
   `CashManagementFlow.net_owner_capital`). These describe *who owns* the
   worth, not *how much* worth exists. They're used in the ownership split
   (section 6), never added to or subtracted from the total itself —
   otherwise investment cash would be double-counted (it already increased
   `cash_in_hand` the moment it was invested).
3. **Cash lost/found, expenses, recurring-expense payments already made,
   tax already paid.** All of these already moved `cash_in_hand` directly
   when they happened — they're baked into that one number, not separate
   line items here.

## 6. Splitting the worth: investors vs. owner

Once Total Business Worth is known, it's divided like this:

```
Investor's Share %  =  Investor.current_worth / Total Business Worth
Owner's Share %      =  100% − (Total Investor Net Worth / Total Business Worth)
```

- `Investor.current_worth` is each investor's stake **compounded by their
  own contracted growth rate**, not a share of the business's actual
  performance. This means an investor's percentage share naturally shrinks
  over time if the business grows faster than their contracted rate — that
  isn't dilution, it's the owner capturing everything above what investors
  are contractually owed. It also means the owner absorbs the downside: if
  the business underperforms, investors still theoretically "grow" at their
  contracted rate, and the owner's share simply gets smaller to compensate.
- **The owner's share can go negative.** If investors' combined
  `current_worth` ever exceeds actual Total Business Worth (e.g. the
  business hasn't grown as fast as investors' contracted rate promised),
  the owner's percentage is shown as negative — mathematically honest,
  not floored at zero. This mirrors `CashManagementFlow.net_owner_capital`,
  which is already allowed to go negative for the same reason (a sole
  owner can draw out more than they've put in, financed by the business).

---

## 7. Why this is safe to compute live, with no dedicated stored model

Every other O(1) dashboard figure in this system (`CashFlow`, `AssetFlow`,
`TaxFlow`, `CashManagementFlow`, `RecurringExpenseFlow`) is a **stored,
incrementally-synced singleton** — updated the instant the underlying event
happens, so reading it never re-scans history. Business Worth doesn't need
its own copy of that machinery, because it does nothing but **read those
already-synced numbers and one bounded live query**:

- Six of the eight components are direct reads of existing O(1) fields —
  effectively free.
- The seventh, Inventory Value, is a live FIFO calculation — but its cost
  scales with **how many distinct products are currently in stock**, not
  with how many years of purchase/sale history exist. That's the same
  reasoning already applied to the Inventory Valuation Report, which also
  has no synced singleton for the same reason.

So Total Business Worth is always exactly current, with no sync code to
maintain and no way for it to drift out of date — it's a pure aggregation,
not a new source of truth.

---

## 8. API reference (for developers)

Requires an authenticated admin or superuser (`is_staff=True` or
superuser) — normal users get a 403.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/profits/business-worth/` | Full worth breakdown (all 8 components + total) plus the ownership split (every investor's worth/share % + owner's worth/share %) |

No backfill command — there's nothing to backfill, since nothing is stored.
