# Cash In Hand — Sources of Inflow & Outflow

The only code allowed to move `cash_in_hand` is `cash_flow/services.py`'s
`_adjust_cashflow()`. Every source below calls into it through a `sync_*`
function, and is mirrored as one row in the `CashMovement` event table
(the "cash in hand" drawer reads only that table).

## Inflows (cash comes in)

| Source | Trigger |
|---|---|
| Opening cash entry | Data-entry opening balance seed |
| Invoice payment | Customer pays an invoice |
| Advance payment (invoice) | Customer pays before/at confirmation |
| Cash found | Manual adjustment — drawer count exceeds books |
| Investor investment | Investor deposits capital |
| Owner contribution | Owner deposits personal money into the business |
| Asset sold | Disposal of a fixed asset (sold, not scrapped) |

## Outflows (cash goes out)

| Source | Trigger |
|---|---|
| Expense | Recorded business expense |
| Supplier payment | Payment to a supplier against a purchase order |
| Advance payment (supplier) | Advance paid to a supplier before confirmation |
| Tax payment | GST paid to FBR |
| WHT payment | Withholding tax paid to FBR |
| Investor profit payout | Profit distributed/paid to an investor |
| Owner profit payout | Profit distributed/paid to the owner |
| Cash lost | Manual adjustment — drawer count short of books |
| Investor withdrawal | Investor pulls capital out |
| Owner drawing | Owner takes personal money out |
| Recurring expense payment | Rent/salary/utility-type recurring expense paid |
| Asset purchase | New fixed asset bought with cash (existing assets don't move cash) |

## Note on profit settlement (Investor/Owner profit payout)

A monthly profit settlement has two distinct actions, and they move cash
differently:

- **Give (payout)** — real cash leaves the business into the investor's/
  owner's pocket. One outflow only. This is a real method-bearing
  transaction — once mandatory method selection exists (see below), the
  user must pick the method(s) here.
- **Reinvest** — the profit never physically leaves; it's booked out as a
  payout and immediately back in as fresh capital (investor investment /
  owner contribution) in the same action. Both legs already net to zero on
  `cash_in_hand`. Once mandatory method selection exists, reinvest must NOT
  prompt the user — both legs default silently to the `Cash` method, since
  no real money moved between real-world accounts.

## Explicitly NOT cash movements

- Customer/supplier returns — inventory value & COGS only; a refund, if any,
  shows up separately as a normal outflow row above.
- Lost/found inventory — inventory value only.
- Invoice/purchase order confirmation — moves what's owed, not cash, until a
  payment is actually made.

## Method field — current state (updated 2026-08-16, real accounts live)

Every one of the original 14 sources, plus every source added since
(assets purchases/sales, recurring expense payments, tax/WHT payments,
cash adjustments, investor/owner transactions and profit payouts), now
records its real payment method(s) through the `payment_methods` app's
allocation engine — see "Real accounts" below. The legacy `method`
CharField on `billing.Payment`/`purchases.SupplierPayment` is still
populated (a derived display label — the single method's name, or
`"multiple"` for a split) for backward-compat readers, but the real,
itemized per-method breakdown lives in `payment_methods.PaymentAllocation`
and is exposed as an `allocations` field on every source's read serializer.

The cash-in-hand drawer (`CashInHandBreakdownView` /
`get_cash_in_hand_breakdown`) derives its `method` column from these real
allocations for every source type, batched per page (fixed 2026-08-16 —
before that fix, 12 of the 14 original source types showed `"N/A"` there
because `CashMovement`'s own frozen `method` snapshot was only ever
populated for invoice/supplier payments, not the rest).

## Real accounts (live, built 2026-08 — `payment_methods` app)

The predefined method choices (jazzcash/easypaisa/bank as free-text labels)
have been replaced by a real `PaymentMethod` model — user-defined accounts
(Cash, JazzCash, Easypaisa, Bank, or anything else added), each with its
own running `balance`. `Cash` ships as a protected, undeletable,
unrenamable seed row (`seed_and_backfill_payment_methods` command).

Every inflow and outflow across billing, purchases, cash_flow (expenses,
opening cash), taxes, profits, cash_management, assets, and
recurring_expenses requires selecting one or more methods (splits allowed
— e.g. an invoice payment of 1000 as 400 Cash + 600 JazzCash), enforced by
`payment_methods.services.record_allocations`/`reverse_allocations`/
`refresh_allocations` — the single choke point for every balance-moving
write. An outflow is rejected if any selected method's balance can't cover
its share. One deliberate exception: a monthly profit settlement's
"Reinvest" action (as opposed to "Give"/payout) silently defaults both its
legs to Cash — no method picker — since no real money crosses accounts,
it's a bookkeeping equity swap.

Transfers between methods (e.g. move 100 from Cash to JazzCash) are
supported via `AccountTransfer` +
`payment_methods.services.transfer_between_methods`, deadlock-safe via
pk-ordered locking across both methods in one transaction. Frontend pages:
`/payment-methods` (method management + balances + per-method history),
`/payment-methods/transfers`.

`cash_in_hand` itself keeps computing exactly as it always has
(untouched) — the per-method balances are a separate, additional
dimension recorded alongside it, not a replacement. Full build history and
phase-by-phase design: `payment_methods/phases.md`. The wiring checklist
for adding a method split to any NEW cash-touching feature:
`instructions/cash-in-hand.md`'s "wire SEVEN places."
