# Production data correction — PO-2026-0001 (2026-08-31)

## What changed

Supplier **PRODUCTION OLD (SUP-001)**'s opening balance record (PO-2026-0001)
was increased by **+2330** to bring in a pre-existing debt that hadn't been
recorded yet. Applied directly against production Postgres via a single
psycopg2 transaction (row-locked with `SELECT ... FOR UPDATE`, not through
the Django ORM), since there is no `update_supplier_opening_balance` service
— this record is create-only by design (see `services.py`).

The value is duplicated across 4 tables (no single source of truth for this
figure), all of which had to be updated together to stay consistent:

| Table | Row | Field | Before | After |
|---|---|---|---|---|
| `purchases_purchaseorder` | id=1 (PO-2026-0001) | `net_payable` | 6722894.0000 | 6725224.0000 |
| | | `payable_outstanding` | 4618800.0000 | 4621130.0000 |
| `data_entry_supplieropeningbalance` | id=1 | `amount` | 6722894.0000 | 6725224.0000 |
| `ledger_supplierledgerentry` | id=1 (opening_balance entry, PRODUCTION OLD's ledger) | `credit` | 6722894.0000 | 6725224.0000 |
| `ledger_supplierledgersnapshot` | id=1 (2026-08) | `closing_balance` | 4618800.0000 | 4621130.0000 |
| `cash_flow_cashflow` | id=1 (singleton) | `supplier_payable_outstanding` | 10081178.5000 | 10083508.5000 |

**Not touched, and don't need to be:**
- `accounting` app's Balance Sheet (Opening Balance Equity) — computed
  **live** from `purchases_purchaseorder.net_payable`
  (`accounting.selectors._compute_equity_offsets`), no stored copy.
- `profits` app's Business Worth — reads `cash_flow_cashflow.supplier_payable_outstanding`
  directly, no separate copy of its own.

Both apps picked up the correction automatically on their next read.

## How to revert

Run these exact statements, in this order, against production:

```sql
UPDATE purchases_purchaseorder SET net_payable = 6722894.0000, payable_outstanding = 4618800.0000 WHERE id = 1;
UPDATE data_entry_supplieropeningbalance SET amount = 6722894.0000 WHERE id = 1;
UPDATE ledger_supplierledgerentry SET credit = 6722894.0000 WHERE id = 1;
UPDATE ledger_supplierledgersnapshot SET closing_balance = 4618800.0000 WHERE id = 1;
UPDATE cash_flow_cashflow SET supplier_payable_outstanding = 10081178.5000 WHERE id = 1;
```

No later ledger snapshot exists for this supplier past 2026-08 as of the
time this change was made — if one now does, a flat revert of the snapshot
row above is no longer correct; `ledger.services._recalculate_snapshots_from`
must be re-run for that ledger from `2026-08` onward instead.
