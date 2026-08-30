# Payment Methods (Accounts) — Build Phases

Goal: replace the predefined method labels (cash/jazzcash/easypaisa/bank)
with a real accounts system — user-defined `PaymentMethod` rows, each with
its own running balance, mandatory selection (with splits) on every
inflow/outflow, insufficient-balance rejection, and transfers between
methods. `cash_in_hand` (`CashFlow`/`CashMovement`) keeps working exactly
as it does today — this is a new, separate dimension recorded alongside it,
not a replacement for it. Full source list: `cash_flow/cash.md`.

Each phase below is its own plan-approval-build-verify cycle — nothing in
a later phase starts until the current one is confirmed working. Phase 0
(this file + app scaffold) is done.

---

## Phase 0 — Scaffold (done)

- `payment_methods` Django app created, registered in `INSTALLED_APPS`.
- This file.

---

## Phase 1 — Core models + CRUD + existing-data backfill (done)

### Models (`payment_methods/models.py`)

Follows this codebase's standard pattern: soft-delete `AuditMixin`
(created_by/updated_by/deleted_by, timestamps, is_deleted,
SoftDeleteManager/AllObjectsManager — copied into this app the same way
billing/purchases each keep their own copy), and a stored, service-updated
running balance (same shape as `cash_management.Investor.net_stake` /
`CashFlow.cash_in_hand` — never recomputed at read time).

```python
class PaymentMethod(AuditMixin):
    name           = CharField(max_length=100, unique=True)
    account_number = CharField(max_length=100, blank=True, default="")
    balance        = DecimalField(max_digits=20, decimal_places=4, default=0,
                          help_text="Running balance for this method. Only ever "
                          "written by payment_methods.services — never at read time.")
    is_protected   = BooleanField(default=False,
                          help_text="True only on the seeded Cash row. Blocks "
                          "rename, is_protected changes, and delete at the service layer.")

    class Meta:
        ordering = ["name"]
```

```python
class PaymentAllocation(models.Model):
    payment_method = ForeignKey(PaymentMethod, on_delete=PROTECT, related_name="allocations")
    source_model   = CharField(max_length=60)   # "billing.payment", "cash_flow.expense", ...
    source_id      = BigIntegerField()
    direction      = CharField(max_length=10, choices=[("inflow","Inflow"),("outflow","Outflow")])
    amount         = DecimalField(max_digits=20, decimal_places=4)
    date           = DateField()
    is_deleted     = BooleanField(default=False, db_index=True)
    created_at     = DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["source_model", "source_id"], name="idx_alloc_source"),
            models.Index(fields=["payment_method", "is_deleted"], name="idx_alloc_method_active"),
        ]
```

No `UniqueConstraint(source_model, source_id)` here (unlike `CashMovement`)
— a split source legitimately produces multiple rows sharing that pair.

```python
class AccountTransfer(AuditMixin):
    from_method = ForeignKey(PaymentMethod, on_delete=PROTECT, related_name="transfers_out")
    to_method   = ForeignKey(PaymentMethod, on_delete=PROTECT, related_name="transfers_in")
    amount      = DecimalField(max_digits=20, decimal_places=4)
    date        = DateField()
    note        = CharField(max_length=255, blank=True, default="")
```

Model built in Phase 1; its create/list/detail API and balance-moving
logic are Phase 6 — kept out of scope here so Phase 1 stays reviewable on
its own.

### Migrations

1. `0001_initial` — the three tables above.
2. A management command (not a baked-in data migration, matching this
   codebase's convention — `backfill_cashflow`, `backfill_cash_movements`
   are commands, not migrations, because their output depends on live
   data, not schema): `seed_and_backfill_payment_methods.py`.
   - Idempotent, safe to re-run: `get_or_create`s the protected `Cash` row
     (`is_protected=True`) rather than failing if it already exists.
   - Sets `Cash.balance = CashFlow.get_instance().cash_in_hand`.
   - For every active `CashMovement` row, `get_or_create`s one matching
     `PaymentAllocation` (`payment_method=Cash`, mirrored
     amount/direction/source_model/source_id/date) — `get_or_create`
     keyed on `(source_model, source_id, payment_method)` makes re-runs a
     no-op instead of duplicating rows.
   - Prints the three numbers side by side for manual verification:
     `Cash.balance`, `CashFlow.cash_in_hand`, `sum(active PaymentAllocation
     for Cash)` — build isn't done until all three agree.

### Services (`payment_methods/services.py`) — Phase 1 scope only

- `create_method(name, account_number, user)` — rejects duplicate names.
- `update_method(method, name=None, account_number=None, user=None)` —
  raises if `method.is_protected`.
- `soft_delete_method(method, user)` — raises if `method.is_protected`,
  raises if `method.balance != 0`.
- No balance-moving logic yet (that's the Phase 2 allocation engine and
  Phase 6 transfer service) — Phase 1 only creates/edits/deletes the
  method rows themselves and runs the backfill.

### API

- `PaymentMethodViewSet` (list/retrieve/create/update/soft-delete),
  `IsAdminOrSuperuser` (matches `cash_management`'s permission pattern —
  accounts are an admin-level concern like Investors).
- Detail serializer includes the method's own transaction history by
  joining its active `PaymentAllocation` rows (read-only in Phase 1 —
  nothing writes new allocations yet outside the backfill).
- `admin.py` registration for both models (ops visibility / manual
  inspection, matching every other app in this codebase).

### Explicitly NOT in Phase 1

- No allocation-writing engine yet (Phase 2).
- No other app (billing, purchases, expenses, ...) wired in — they keep
  working exactly as today.
- No transfer API (model exists, endpoints don't yet).
- `cash_in_hand` computation completely untouched.

### Tests

- `PaymentMethod`: unique name constraint, protected-row rename/delete
  blocked, delete blocked while `balance != 0`, delete allowed at exactly
  `balance == 0`.
- Backfill command: creates exactly one `Cash` row on first run, is a
  no-op on a second run (row counts unchanged), the three-way balance
  cross-check passes against a seeded local dataset.
- API: non-admin roles get 403; admin can create/edit/delete methods
  through the normal flow; protected-row edit/delete attempts return a
  clean 400, not a 500.

---

## Phase 2 — Allocation engine (the atomic core) (done)

The single choke point every future phase calls into — mirrors
`cash_flow/services.py`'s `_adjust_cashflow` +
`record_cash_movement`/`refresh_cash_movement`/`reverse_cash_movement`
pattern exactly (same `source` object → `_source_label(source)` +
`source.pk` convention), so it fits how the rest of the codebase already
works. Lives in `payment_methods/services.py`, alongside the Phase 1
method CRUD functions.

### `record_allocations(source, *, direction, splits, total_amount, date, user)`

The ONLY function allowed to write `PaymentAllocation` rows and adjust
`PaymentMethod.balance`. `source` is the model instance that caused the
transaction (an `Expense`, a `Payment`, ...) — same object every
`sync_*`/`record_cash_movement` call already receives. `splits` is
`[(payment_method, amount), ...]` — resolved `PaymentMethod` instances,
not raw IDs (the caller's serializer resolves them first, same as
`InvestorTransactionWriteSerializer.investor` already does).

Validation, in order, all inside one `@transaction.atomic` block:
1. `total_amount > 0`, `splits` non-empty, every leg `amount > 0`.
2. No method repeated across legs.
3. `sum(leg amounts) == total_amount` exactly (Decimal equality — no
   rounding slack).
4. Lock every distinct `PaymentMethod` touched in one query —
   `select_for_update().filter(pk__in=...).order_by("pk")` — the `order_by`
   is deliberate: every caller locks methods in the same pk order, so two
   concurrent multi-method transactions can never deadlock on each other.
5. **Outflow only**: for every leg, check `amount <= method.balance`.
   Collect *every* shortfall found, not just the first — the error the
   user sees lists every method that's short, not one at a time.
6. If step 5 found any shortfall: raise
   `rest_framework.exceptions.ValidationError` (matches this codebase's
   existing convention — `cash_management`/`cash_flow`/`billing` services
   all raise this directly, no dedicated exception class) with one message
   per method, e.g. `"JazzCash only has Rs. 150.00, this outflow needs Rs.
   600.00 from it."` Nothing is written — the `@transaction.atomic` wrapper
   plus the exception means the whole call rolls back, never a
   partially-applied split.
7. Otherwise: create one `PaymentAllocation` row per leg, and adjust each
   locked `PaymentMethod.balance` (`+=` for inflow, `-=` for outflow) —
   **not floored at 0**, deliberately, mirroring `_adjust_cashflow`'s own
   documented reasoning: outflow legs are already balance-checked in step
   5 so a fresh outflow can never push a method negative on its own, but a
   *reversal* of a past inflow (see below) legitimately can, and that's
   real information worth seeing, not something to silently clamp away.

Returns the list of created `PaymentAllocation` rows.

### `reverse_allocations(source)`

Mirrors a source's soft-delete — finds every active `PaymentAllocation`
for `(source_model, source_id)`, locks their methods (same ordered-lock
rule as above), undoes each leg's balance effect (an inflow reversal
subtracts, an outflow reversal adds back), and soft-deletes the allocation
rows. No insufficient-balance check here — reversing an inflow is allowed
to take a method negative (that negative balance is the honest signal that
the money was already spent elsewhere before the original entry got
deleted; same "don't clamp, don't hide" philosophy `_adjust_cashflow`
already uses for `cash_in_hand`). No-op if no allocations exist for that
source.

### `refresh_allocations(source, *, direction, splits, total_amount, date, user)`

For edits that change the split (e.g. an advance capped at confirmation —
the exact scenario the billing advance-cap fix already handles for
`cash_in_hand`). Implemented as `reverse_allocations(source)` followed by
`record_allocations(source, ...)` inside one atomic block — reversing
first means the new split's balance check runs fairly (the old legs'
money is already back before the new legs are validated against it).

### Explicitly NOT in Phase 2

- No app is wired to call this engine yet (Phase 3+) — it exists and is
  fully tested in isolation, nothing creates real `splits` from a live
  form yet.
- No transfer function — `AccountTransfer`'s balance-moving logic is
  Phase 6, a sibling function with its own two-method lock, not part of
  this engine.

### Tests

- Single-method inflow and outflow, balance moves correctly.
- Split inflow across 2+ methods — every method's balance updates by its
  own leg, not the total.
- Split outflow where one leg is short — the whole call raises, **zero**
  methods' balances change (verified via `refresh_from_db`), and the error
  message names the specific short method and both numbers.
- Split outflow where *two* legs are short — both show up in the one
  error, not just the first.
- `sum(splits) != total_amount` rejected.
- Same method repeated across two legs rejected.
- `reverse_allocations` undoes a multi-method split correctly, including
  the case where reversing an inflow leg is allowed to take that method
  negative (asserted as allowed, not raised).
- `refresh_allocations` moving a split (e.g. 400 Cash + 600 JazzCash → 300
  Cash + 700 JazzCash) leaves both methods at the exactly-right new
  balance, and still enforces the balance check on the new split.
- Locking order: a regression test asserting `record_allocations` always
  issues its `select_for_update` sorted by method pk regardless of the
  order methods appear in `splits` (guards the deadlock-avoidance
  guarantee, not just the balance math).

---

## Phase 3 — Wire into Billing + Purchases (done)

Traced every call site in `billing/services.py` and `purchases/services.py`
that touches `Payment`/`SupplierPayment` — 4 decisions to nail down before
touching code, then a concrete wiring map for every site.

### Decision 1 — the legacy `method` CharField

`Payment.method`/`SupplierPayment.method` stay on the models (reports,
serializers, PDFs already read `.method`/`get_method_display` — not worth
touching every caller). They become **derived, not user-input**: the
create service sets `method = allocations[0].payment_method.name.lower()`
if there's exactly one leg, else `method = "multiple"`. The
`Method.TextChoices` constraint is dropped (any account name can land
here now, not just the old 4) — becomes a plain `CharField`. No serializer
exposes it as writable any more; `method_allocations` replaces it as the
real input.

### Decision 2 — draft-time advance payment method

Today `create_invoice`/`create_purchase_order` hardcode the draft-time
advance to `Payment.Method.CASH` (`billing/services.py:448`) — no user
choice. Since an advance is real cash moving on draft creation, this
becomes mandatory + splittable too, same as a regular payment — the
hardcoding goes away.

### Decision 3 — advance amount edited while still draft

`update_invoice`/`update_purchase_order` let `advance_amount` change
before confirmation (`_update_advance_payment`). If the amount changes,
the method split must be re-collected from the user, not silently reused
at the old proportions — a bigger or smaller advance may need different
accounts entirely. `refresh_allocations` handles this once the caller
passes the new split.

### Decision 4 — advance capped at confirmation (billing only)

`confirm_invoice` auto-caps an over-large advance down to `grand_total`
(the fix from earlier this session) via `_update_advance_payment`. The
user never re-picks a method here — it's an automatic system correction,
same as today. The original split gets shrunk **pro-rata** across every
leg it already had, using largest-remainder rounding to keep the legs
summing to the new capped total exactly (4 decimal places) — the same
class of drift the "29,999.996" bug came from, so this must be exact, not
approximate.

`purchases.confirm_purchase_order` has the equivalent net_payable cap
(`purchases/services.py:1112-1116`) but — confirmed by reading it — it
only caps `order.advance_amount`, it never trims the actual
`SupplierPayment.amount`/cash/allocations the way billing's does. That's
a pre-existing asymmetry between the two apps, not something Phase 3
introduces or is meant to fix (changing it would be a business-logic
change needing its own separate approval per project rules) — so the
purchases side needs no pro-rata trim logic, only billing does.

### Wiring map

| Function | App | Direction | Allocation call |
|---|---|---|---|
| `create_payment` | billing | inflow | `record_allocations` |
| `delete_payment` | billing | — | `reverse_allocations` |
| `create_invoice` (advance block) | billing | inflow | `record_allocations` |
| `_cancel_advance_payment` | billing | — | `reverse_allocations` |
| `_update_advance_payment` | billing | inflow | `refresh_allocations` (user split on amount-edit; pro-rata split on confirm-cap) |
| `create_supplier_payment` | purchases | outflow | `record_allocations` |
| `delete_supplier_payment` | purchases | — | `reverse_allocations` |
| `create_purchase_order` (advance block) | purchases | outflow | `record_allocations` |
| `_cancel_advance_payment` | purchases | — | `reverse_allocations` |
| `_update_advance_payment` | purchases | outflow | `refresh_allocations` |

Every call sits right next to the existing `record_cash_movement`/
`reverse_cash_movement`/`refresh_cash_movement` call in the same
transaction — same pattern `instructions/cash-in-hand.md` already
documents for wiring a new cash-touching feature, just a second call
alongside the first. `cash_in_hand` itself is untouched; the allocation
engine's insufficient-balance check on outflows (supplier payments) is a
**new**, additional rejection reason on top of the existing
`payable_outstanding` check — a supplier payment can now fail even when
the invoice/order side is fine, if the chosen outflow method doesn't have
the funds.

### API changes

- `PaymentWriteSerializer`/`SupplierPaymentWriteSerializer`: `method`
  field replaced with `method_allocations = [{"payment_method": id,
  "amount": Decimal}, ...]`, validated non-empty and each amount positive
  (the sum-matches-total and balance checks live in the Phase 2 engine,
  not duplicated in the serializer).
- `InvoiceCreateSerializer`/`PurchaseOrderCreateSerializer`: when
  `payment_type == "advance"`, `method_allocations` becomes required
  alongside `advance_amount`.
- `PaymentReadSerializer`/`SupplierPaymentReadSerializer`: add an
  `allocations` field (nested `PaymentAllocationReadSerializer` list) so
  the frontend can show the real split, not just the derived `method`
  string.

### Frontend

- Multi-row method+amount picker on: invoice payment form, supplier
  payment form, invoice draft creation (advance), purchase order draft
  creation (advance), and the advance-amount edit form.
- Running "remaining to allocate" total; submit disabled until it hits
  exactly zero.
- Server-side insufficient-balance errors surfaced inline against the
  specific method row that's short, not as a generic toast.

### Tests

- `create_payment`/`create_supplier_payment`: split across 2+ methods
  creates matching `PaymentAllocation` rows and moves each method's
  balance; single-method still works (not a forced split).
- Supplier payment outflow rejected when the chosen method is short —
  existing `payable_outstanding` check still passes but the call is
  rejected anyway; no `SupplierPayment` row, no allocation, no balance
  change (mirrors the Phase 2 abort-everything guarantee end-to-end).
- Delete reverses allocations exactly (`reverse_allocations` called,
  method balances restored).
- Draft advance payment now requires and honors `method_allocations`
  instead of being hardcoded to Cash.
- Advance-amount edited pre-confirmation: old split fully reversed, new
  split (possibly different methods) applied.
- Advance-cap-at-confirmation pro-rata test: a 3-way split advance
  (Cash/JazzCash/Bank) gets capped down, every leg shrinks proportionally,
  and the three shrunk legs still sum to EXACTLY the new capped total to
  4 decimal places (largest-remainder rounding verified, not just "close
  enough").
- Regression: full `billing`/`purchases`/`cash_flow`/`ledger`/
  `credit_score` suites still pass — this phase must not change any dollar
  figure anywhere, only add the method dimension alongside it.

---

## Phase 4 — Profit settlement exception (done)

Traced both payout functions in `profits/services.py` —
`create_investor_profit_payout` and `create_owner_profit_payout` — which
are exact mirrors of each other (one against `MonthlyProfitInvestorShare`,
one against `MonthlyProfitOwnerShare`). Both already branch on
`action_type` (`payout` vs `reinvest`), and reinvest already calls into
`cash_management.services.create_investor_transaction` /
`create_owner_transaction` internally to book the offsetting inflow — so
the "give vs reinvest" split this phase needs is exactly the branch that
already exists, just adding the method dimension to it.

### Give (payout) — mandatory method selection

`method_allocations` becomes a required param, validated only when
`action_type == "payout"`. Wired into `record_allocations(payout,
direction="outflow", splits=method_allocations, total_amount=amount,
date=payout_date, user=user)`, right next to the existing
`record_cash_movement(payout)` call — same "every cash-touching feature
wires both together" rule as everywhere else. Split allowed, same as any
other outflow; rejected if the chosen method(s) can't cover it.

### Reinvest — silent, both legs default to Cash

No picker shown to the user, per your instruction — the money never
physically leaves, it's a bookkeeping swap of equity (profit share →
capital). `method_allocations` is not required or read for this branch;
the function resolves the protected `Cash` `PaymentMethod` itself and
calls `record_allocations(payout, direction="outflow", splits=[(cash,
amount)], ...)` for the payout's own leg.

**Cross-phase dependency, flagged now so it isn't a surprise later:**
reinvest's *inflow* leg happens inside `create_investor_transaction`/
`create_owner_transaction` (in `cash_management/services.py`) — functions
this phase does not touch. Right now they take no `method_allocations` at
all, so the inflow leg records no allocation (fine — no source model
existed for that path before Phase 5). Once Phase 5 makes
`InvestorTransaction`/`OwnerTransaction` require a method like every other
source, this reinvest call site must be updated in the *same* change to
pass the Cash default explicitly (`method_allocations=[(cash, amount)]`)
— otherwise reinvest would suddenly demand a method pick from the user,
which is exactly what this phase is turning off. Noting it here so Phase
5's plan accounts for it up front instead of it being discovered as a
regression.

### API changes

- `InvestorProfitPayoutWriteSerializer`/`OwnerProfitPayoutWriteSerializer`:
  add `method_allocations` (same `MethodAllocationInputSerializer`,
  `required=False`), with a `validate()` requiring it only when
  `action_type == "payout"` — mirrors the exact pattern already used for
  `InvoiceCreateSerializer`'s advance-amount/method_allocations pairing in
  Phase 3.
- Read serializers gain an `allocations` field (same
  `SerializerMethodField` pattern as `PaymentReadSerializer`) so the give
  path shows its real split; reinvest rows will just show the single Cash
  allocation.

### Delete path

`delete_investor_profit_payout`/`delete_owner_profit_payout` call
`reverse_allocations(payout)` next to the existing
`reverse_cash_movement(payout)` — covers both action types uniformly,
since both always wrote exactly one payout-leg allocation set (single
Cash leg for reinvest, user's chosen split for payout). The reinvest
inflow leg's own reversal already cascades automatically today via the
existing `delete_investor_transaction(...)`/`delete_owner_transaction(...)`
call inside these functions — once Phase 5 wires that function's own
`reverse_allocations`, it fires for free through this same cascade, no
extra call needed here.

### Frontend

- Payout form: method picker (with split) shown ONLY when "Give" is
  selected; hidden entirely when "Reinvest" is selected — the toggle
  between the two actions should visibly hide/show the picker, not just
  leave it optional, so it's clear to the user reinvest doesn't ask.

### Tests

- Give with a single method and with a split — payout's own allocation
  matches, method balance moves.
- Give with an insufficient method — rejected, no payout row, no share
  balance change (mirrors the Phase 3 supplier-payment rejection test
  shape).
- Reinvest — no `method_allocations` passed by the caller at all, payout's
  Cash allocation is created automatically, Cash balance drops by the
  outflow leg (the offsetting inflow leg is out of scope until Phase 5,
  so Cash's net effect from a reinvest stays what it already was: the
  payout-out is real, the transaction-in isn't allocation-tracked yet).
- Delete reverses the payout's own allocation for both action types.
- Regression: full `profits`/`cash_management` suites unaffected in dollar
  terms — only the method dimension is new.

---

## Phase 5 — Remaining 10 source models (done)

Correction to the earlier "9" estimate: Phase 3 covered 2 of the 14
`cash_flow/cash.md` source models (`billing.Payment`,
`purchases.SupplierPayment`) and Phase 4 covered 2 more
(`profits.InvestorProfitPayout`, `profits.OwnerProfitPayout`) — 10 remain,
across 6 apps. Same mandatory-selection treatment as Phase 3 throughout:
`method_allocations` required, wired into `record_allocations`/
`reverse_allocations` next to the existing `record_cash_movement`/
`reverse_cash_movement` calls, in the same transaction.

Split into 5 independently-approvable batches — smallest/lowest-risk
first, so each is reviewable on its own instead of one 10-model change:

### Batch A — `cash_management` (3 models, resolves the Phase 4 dependency)

| Function | Model | Direction |
|---|---|---|
| `create_cash_adjustment` / `delete_cash_adjustment` | `CashAdjustment` | inflow (found) / outflow (lost) — direction depends on `adjustment_type`, decided per-call same as today |
| `create_investor_transaction` / `delete_investor_transaction` | `InvestorTransaction` | inflow (investment) / outflow (withdrawal) |
| `create_owner_transaction` / `delete_owner_transaction` | `OwnerTransaction` | inflow (contribution) / outflow (drawing) |

**This batch must also update `profits/services.py`'s two reinvest call
sites** (`create_investor_transaction`/`create_owner_transaction` calls
inside `create_investor_profit_payout`/`create_owner_profit_payout`) in
the *same* change — passing `method_allocations=[(cash, amount)]`
explicitly, resolving the cross-phase dependency flagged in Phase 4's plan.
Skipping this would make reinvest suddenly demand a method pick, which is
exactly the behavior Phase 4 turned off.

`create_investor_transaction` has an `is_data_entry` flag that already
skips the `cash_in_hand` sync entirely (opening-balance capital that was
never really in the till) — mirror that: `is_data_entry=True` calls also
skip the method requirement, since there's no real cash movement to
allocate.

### Batch B — `taxes` (2 models, simplest batch — no update path exists)

| Function | Model | Direction |
|---|---|---|
| `create_tax_payment` / `delete_tax_payment` | `TaxPayment` | outflow |
| `create_wht_payment` / `delete_wht_payment` | `WHTPayment` | outflow |

Both are the plainest shape in the whole rollout: create → deduct, delete
→ restore, no edit/update function, no advance/cap complexity. Good
batch to build first as the template the others follow.

### Batch C — `assets` (2 models, conditional — not every row moves cash)

| Function | Model | Direction | Condition |
|---|---|---|---|
| `create_asset` | `Asset` | outflow | only when `acquisition_type == "new"` (an "existing" asset never touches cash — `method_allocations` not required in that case) |
| `dispose_asset` | `AssetDisposal` | inflow | only when `disposal_type == "sold"` (scrapped is an audit record only) |

Mirrors the conditional pattern Phase 3/4 already established
(`payment_type == "advance"`, `action_type == "payout"`) — required only
on the branch that actually moves cash.

### Batch D — `recurring_expenses` (1 model)

| Function | Model | Direction |
|---|---|---|
| `create_recurring_expense_payment` / `delete_recurring_expense_payment` | `RecurringExpenseAssignmentPayment` | outflow |

Same plain shape as Batch B — outflow only, existing overpayment guard
(`amount > outstanding`) untouched, `record_allocations`'s balance check
is a new, additional rejection reason layered on top, same as Phase 3's
supplier payments.

### Batch E — `cash_flow` + `data_entry` (2 models)

| Function | Model | Direction |
|---|---|---|
| `create_expense` / `update_expense` / `delete_expense` | `Expense` | outflow |
| `create_opening_cash` | `OpeningCashEntry` | inflow |

`update_expense` is the one function in this whole phase with an amount
EDIT path (not just create/delete) — needs `refresh_allocations`, same
shape as Phase 3's advance-amount edits, but simpler (no pro-rata cap
case, the user just re-picks the split for the new amount directly).

`OpeningCashEntry` is a one-time bootstrap flow (`data_entry` is
documented elsewhere as "a removable bootstrap app" — optional post-go-live).
Worth confirming before building: does it get the full mandatory-method
treatment like everything else, or is it low-value enough to leave
optional/defaulted-to-Cash since it's rarely used after initial setup?
Flagging as a decision point rather than assuming.

### Cutting across all 5 batches

- Serializer pattern: every write serializer gets `method_allocations`
  (required unconditionally, or required only on the cash-moving branch
  for Batch C) — same `MethodAllocationInputSerializer` used since Phase 3.
- Read serializer pattern: every read serializer gets an `allocations`
  field. **Watch for the N+1 this phase's own Phase 4 build hit** — any
  of these models shown in a nested/list context (not just a standalone
  retrieve) needs the batched `get_allocations_by_source_ids` +
  serializer-context pattern from `MonthlyProfitDetailView`, not a live
  per-object query in `get_allocations`. Check each list/detail view this
  phase touches for that shape before shipping.
- View pattern: same `_as_splits()` helper, one per app (already exists in
  `billing/views.py`, `purchases/views.py`, `profits/views.py` — Batches
  A/B/C/D/E each need their own copy, or this becomes the first real case
  for promoting `_as_splits` into a shared home, e.g.
  `payment_methods/views.py`, imported everywhere instead of copy-pasted
  a 5th/6th/7th time).

### Tests

- One create/delete round-trip per model, with a split and with a
  single method, matching Phase 3/4's shape.
- Conditional-branch tests for Batch C (existing-acquisition asset needs
  no method; new-acquisition does; scrapped disposal needs no method;
  sold does).
- Batch A's reinvest-still-silent regression test — after this batch
  lands, re-run Phase 4's `test_reinvest_needs_no_method_allocations_and_
  defaults_to_cash` and confirm it still passes unchanged (proves the
  cross-phase dependency was actually resolved, not just documented).
- Full project regression after each batch (not just at the end of
  Phase 5) — 5 checkpoints instead of 1, so a break is caught against the
  batch that caused it.

---

## Phase 6 — Transfers (done)

The `AccountTransfer` model already exists (Phase 1) with `from_method`,
`to_method` (both `PROTECT`), `amount`, `date`, `note`. The key design
insight: a transfer's two legs — money leaving `from_method`, money
landing in `to_method` — are each exactly what `record_allocations`
already knows how to write and balance-check. Rather than build a second,
parallel balance-moving engine, `transfer_between_methods` calls the
Phase 2 engine **twice** against the same `AccountTransfer` row as its
`source`, reusing 100% of its locking, validation, and insufficient-
balance rejection — no new balance-math code at all.

### `transfer_between_methods(*, from_method_id, to_method_id, amount, date, note="", user)`

```python
@transaction.atomic
def transfer_between_methods(*, from_method_id, to_method_id, amount, date, note="", user):
    if from_method_id == to_method_id:
        raise ValidationError({"to_method": "Cannot transfer a method to itself."})
    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})

    from_method = get_object_or_404(PaymentMethod, pk=from_method_id, is_deleted=False)
    to_method   = get_object_or_404(PaymentMethod, pk=to_method_id, is_deleted=False)

    # Pre-lock BOTH rows together, sorted by pk — see deadlock note below.
    _lock_methods(sorted([from_method_id, to_method_id]))

    transfer = AccountTransfer.objects.create(
        from_method=from_method, to_method=to_method, amount=amount,
        date=date, note=note, created_by=user, updated_by=user,
    )

    record_allocations(transfer, direction="outflow", splits=[(from_method, amount)],
                        total_amount=amount, date=date, user=user)
    record_allocations(transfer, direction="inflow", splits=[(to_method, amount)],
                        total_amount=amount, date=date, user=user)

    return transfer
```

**Deadlock note** — the plan explicitly calls this out because Phase 2's
own ordered-locking rule exists for exactly this scenario: if
`transfer_between_methods` just called `record_allocations` twice without
pre-locking, each call would lock only its own method in isolation. Two
concurrent transfers in *opposite* directions between the same two methods
(A→B and B→A) would then lock in opposite orders and deadlock. Pre-locking
`sorted([from_method_id, to_method_id])` in one call up front — before
either `record_allocations` call — makes the two inner locks no-ops
(already held by the same transaction) and guarantees every transfer
locks these two rows in the same global order, regardless of direction.

**Balance check comes free**: the outflow `record_allocations` call
already rejects if `from_method` can't cover `amount`, with the same
"JazzCash only has X" error shape every other outflow uses. Nothing new
to test there beyond confirming it fires for transfers too.

**`cash_in_hand` is untouched** — no `sync_*`/`record_cash_movement` call
anywhere in this function. Confirmed by design: a transfer moves which
account holds the money, not whether the business has it.

### `delete_account_transfer(*, pk, user)`

Also close to free: soft-delete the `AccountTransfer` row, then call the
existing `reverse_allocations(transfer)` — it already finds both legs
(same `source_model`/`source_id`, one per method), locks both methods
together (its own internal `_lock_methods`), and reverses each by its
recorded direction. No new reversal logic needed.

### API

- `AccountTransferListCreateView` (`AllocationsListMixin`, same batched-
  context N+1 guard as every other Phase 3–5 list view — a transfer's two
  legs are worth showing per-row same as anywhere else).
- `AccountTransferRetrieveDestroyView` — `GET`/`DELETE`.
- `AccountTransferWriteSerializer`: `from_method`, `to_method`, `amount`,
  `date`, `note` — no `method_allocations` field needed here, unlike every
  other Phase 3–5 source — the whole point of a transfer IS picking the
  two methods directly.
- `AccountTransferReadSerializer`: adds `allocations` (both legs) for
  symmetry with every other read serializer, though for a transfer this
  is informational — the two `PaymentAllocation` rows literally mirror
  `from_method`/`to_method`/`amount` already on the row itself.

### Tests

- Successful transfer moves both methods' balances by exactly `amount`,
  writes exactly 2 `PaymentAllocation` rows (one outflow, one inflow) tied
  to the same transfer.
- Self-transfer (`from_method_id == to_method_id`) rejected.
- Insufficient `from_method` balance rejected, same error shape as every
  other outflow rejection — and confirms **zero** balance change on
  either method (all-or-nothing, matching Phase 2's guarantee).
- Delete reverses both methods' balances back exactly and soft-deletes
  both `PaymentAllocation` legs.
- Lock-ordering regression: assert `transfer_between_methods` always
  locks `[from_method_id, to_method_id]` sorted by pk regardless of which
  direction the transfer runs — mirrors Phase 2's own lock-ordering test,
  guards the deadlock fix specifically, not just the balance math.
- Query-count test for the list view, same shape as every other Phase 3–5
  batch.

### Frontend

- Dedicated transfer action/page ("move 100 from Cash to JazzCash") — a
  simple two-method-picker + amount form, no split UI needed (a transfer
  has exactly one from and one to, by definition).

---

## Phase 7 — Frontend completion (done)

- Method management page: create/edit/soft-delete `PaymentMethod` rows,
  each showing its balance and transaction history.
- Every remaining inflow/outflow entry form across the app gets its
  dropdown (the forms wired server-side in Phases 3–5 get their UI here if
  not already done alongside).
- Transfers page.

---

## Phase 8 — Verification & cleanup (done, minus the invariant check — explicitly skipped, see below)

- Full regression: billing, purchases, cash_flow, accounting, profits,
  assets, cash_management, taxes, recurring_expenses, payment_methods,
  data_entry test suites — run 2026-08-16, 286 tests, all passing.
- New standing invariant check (`cash_in_hand == sum(all PaymentMethod
  balances)`, alongside the Balance Sheet `is_balanced` check) —
  **deliberately NOT built**, per explicit instruction ("don't need to
  check the balance sheet"). No automated cross-check exists yet; don't
  assume one is catching drift between `cash_in_hand` and the sum of
  `PaymentMethod` balances.
- Updated `instructions/cash-in-hand.md`: added step 7 to the checklist
  (now "wire SEVEN places") — any new cash-touching feature must also call
  the Phase 2 allocation engine on create/edit/delete, same as it already
  must wire `CashMovement`.
- Updated `cash_flow/cash.md`'s "Planned: real accounts" section — now
  "Real accounts (live, built 2026-08)", describing the system as built,
  not planned.
