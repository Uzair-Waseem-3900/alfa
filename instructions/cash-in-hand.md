# New cash-touching feature → wire SEVEN places, same pass

1. Live sync function in `cash_flow/services.py`. (This ensures the number moves in real time)
2. A payload builder in `cash_flow/services.py`'s `_MOVEMENT_BUILDERS` map, plus
   `record_cash_movement(source)` at the create site and
   `reverse_cash_movement(source)` at the delete/reversal site (and
   `refresh_cash_movement(source)` if the source's amount/display fields are
   editable). This is what makes the row appear in the cash-in-hand drawer —
   the drawer reads ONLY the `CashMovement` event table now.
3. The same source loop in `management/commands/backfill_cash_movements.py`.
   (Otherwise re-running the rebuild silently drops those rows.)
4. Line item in `get_cash_in_hand_breakdown_from_sources()`
   (`cash_flow/selectors.py`) — the consistency oracle tests compare the
   event table against.
5. `backfill_cashflow.py`. (Otherwise re-running it silently undoes the
   deduction/addition.)
6. Classify the new `movement_type` in `accounting/selectors.py`'s
   `OPERATING_MOVEMENT_TYPES` / `INVESTING_MOVEMENT_TYPES` /
   `FINANCING_MOVEMENT_TYPES` sets, and give it a human label in
   `_MOVEMENT_TYPE_LABELS`. Skipping this does NOT just omit a line from the
   Cash Flow Statement — `net_change_in_cash` is summed from those buckets
   and `opening_cash` is derived as `closing_cash - net_change`, so an
   unclassified type makes both totals wrong. Since 2026-08-15 an unmapped
   type falls into Operating labelled `"Unclassified — <movement_type>"`
   rather than being dropped, so the totals stay correct and the gap is
   visible on the statement — but that's a safety net, not a substitute for
   classifying it properly here.

7. The Phase 2 allocation engine (`payment_methods.services.
   record_allocations`/`reverse_allocations`/`refresh_allocations`) — the
   real multi-account ledger (`payment_methods.PaymentMethod.balance`),
   separate from `cash_in_hand` but required to move in the SAME
   transaction, same as the `CashMovement` event in step 2.
   `record_allocations(source, direction=..., splits=method_allocations,
   total_amount=..., date=..., user=...)` sits right next to
   `record_cash_movement(source)` at the create site;
   `reverse_allocations(source)` sits next to `reverse_cash_movement(source)`
   at the delete/reversal site; `refresh_allocations(...)` sits next to
   `refresh_cash_movement(source)` wherever the amount/date can change after
   creation. The write serializer must require `method_allocations`
   whenever the feature genuinely moves cash (see `payment_methods/
   phases.md`'s per-source-model table for the exact "required only when"
   condition each existing feature uses — e.g. `acquisition_type=="new"`,
   `disposal_type=="sold"`, `action_type=="payout"` not `"reinvest"`).
   Skipping this leaves `PaymentMethod` balances silently out of sync with
   the money the feature actually moved. Conceptually, `cash_in_hand`
   should always equal `sum(all PaymentMethod balances)` — there is no
   automated check enforcing this yet, so don't rely on one catching a
   missed wiring; get step 7 right at write time.

Events are written in the SAME transaction as the CashFlow adjustment —
never record an event without its cash sync or vice versa. The same rule
applies to step 7's allocation calls.
