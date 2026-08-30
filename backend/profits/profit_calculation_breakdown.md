# Profit Calculation Deep Dive — AlphaPK

## The Big Picture Formula

For every finalized month, the net profit is calculated as:

```
Net Profit =
    net_gross_profit          ← Sales Revenue - COGS, adjusted for returns
  - expenses_paid             ← Regular expenses dated THIS month
  - recurring_expenses_paid   ← Recurring expense payments dated THIS month
  - gst_paid                  ← GST paid to FBR dated THIS month
  - wht_paid                  ← WHT deposited to FBR dated THIS month
  - lost_cash                 ← Cash marked LOST, dated THIS month
  + found_cash                ← Cash marked FOUND, dated THIS month
  - lost_inventory            ← Inventory marked LOST, dated THIS month (batch created this month)
  + found_inventory           ← Inventory recovered, dated THIS month (regardless of when originally lost)
  - depreciation              ← Depreciation entries FOR THIS month's period
  + disposal_gain_loss        ← Asset disposal gain/loss dated THIS month
```

> [!NOTE]
> Lost and found are **never netted before storage** — each of the four values is computed and stored independently, dated by when it actually happened. This is deliberate: a single "net" number was confusing (see the "Known Limitation" this replaced, below), and it broke for inventory recoveries that happened after the original loss's month was already finalized. See section 6/7 for exactly how each is dated.

> [!IMPORTANT]
> **Every single deduction below is scoped ONLY to that specific month's date range (`first_day` → `last_day`).
> Nothing is accumulated "from start to today". Each month is its own independent slice.**

---

## Component-by-Component Breakdown

---

### 1. `net_gross_profit` (starting point)

**Source:** `get_gross_profit_trend()` in `cash_flow/selectors.py`

**How it works:**
- Queries all **confirmed, non-data-entry invoices** with `confirmed_at` falling within this month
- Sums: `grand_total` → gross revenue, `total_cogs` → gross COGS, `gross_profit`
- Separately queries **accepted customer returns** with `accepted_at` falling within this month
- Then computes:
  ```
  net_revenue      = revenue      - return_value   (return recognized in the month it was ACCEPTED)
  net_cogs         = cogs         - return_cogs
  net_gross_profit = net_revenue  - net_cogs
  ```

> [!NOTE]
> A return accepted in July always reduces July's profit — even if the original sale was in June. The return is recognized when it's accepted, not when the sale was made.

---

### 2. `expenses_paid`

**Source:** `_compute_expenses_paid()` — queries `Expense` model

**Scope:** Only expenses whose `expense_date` falls within this month.

✅ **Month-specific only.**

---

### 3. `recurring_expenses_paid`

**Source:** `_compute_recurring_expenses_paid()` — queries `RecurringExpenseAssignmentPayment`

**Scope:** Only recurring expense payments whose `payment_date` falls within this month.

✅ **Month-specific only.**

---

### 4. `gst_paid`

**Source:** `_compute_gst_paid()` — queries `TaxPayment`

**Scope:** Only GST payments to FBR whose `payment_date` falls within this month.

✅ **Month-specific only.**

---

### 5. `wht_paid`

**Source:** `_compute_wht_paid()` — queries `WHTPayment`

**Scope:** Only WHT deposits whose `payment_date` falls within this month.

✅ **Month-specific only.**

---

### 6. `lost_inventory` / `found_inventory`

**Sources:**
- `_compute_lost_inventory()` — sums `total_lost_amount` for `LostInventoryRecord` rows whose `created_at__date` falls within this month.
- `_compute_found_inventory()` — sums `recovered_amount` for `LostInventoryRecovery` rows whose `recovered_at` falls within this month.

`LostInventoryRecovery` is a **dated ledger row created every time `mark_lost_inventory_found()` runs** — one row per "mark as found" action, storing `quantity`, `recovered_amount` (snapshotted `unit_cost × quantity` for that specific find), and `recovered_at` (the date it happened). It's the dated counterpart to `LostInventoryItem.found_quantity`, which is just a running counter with no timestamp of its own.

**How this fixes the old limitation:** previously, "found" had no date — a recovery could only ever reduce the number in the month the *original loss* was recorded in, which broke silently once that month was already finalized/frozen. Now, a loss dated June and a recovery dated July show up exactly where they belong:
- June: `lost_inventory` includes the full loss. `found_inventory` is 0 (nothing recovered yet in June).
- July: `lost_inventory` is unaffected (no new loss batch created in July). `found_inventory` includes the July recovery, which **adds back to July's profit** — it does not reach back and change June's already-frozen number.

If July also has its own new losses, they add to `lost_inventory` independently — lost and found are never netted against each other before storage.

✅ **Each side is independently month-specific, dated by when it actually happened.**

---

### 7. `lost_cash` / `found_cash`

**Sources:**
- `_compute_lost_cash()` — sums `CashAdjustment` LOST rows whose `adjustment_date` falls within this month.
- `_compute_found_cash()` — sums `CashAdjustment` FOUND rows whose `adjustment_date` falls within this month.

Same shape as inventory above — each side computed and stored independently, never netted before storage. This was already date-symmetric before the redesign (cash adjustments always carried their own `adjustment_date`); the fields were simply renamed and un-netted to match the new inventory-side convention and the same "don't show a net, show both sides" UI requirement.

✅ **Month-specific only, both sides. No accumulation.**

---

### 8. 🔴 `depreciation`

**Source:** `_compute_depreciation()` — queries `AssetValuationEntry`

**Scope:** Only `AssetValuationEntry` rows where `period = "YYYY-MM"` (the exact period being calculated).

**Important detail:** Before profit catch-up runs, `assets.selectors.get_asset_stats()` is called first (line ~301 in services.py) to ensure asset depreciation entries are written for all past periods. Then the depreciation query picks up only this month's entries.

✅ **Month-specific only. Each month gets its own depreciation entry.**

---

### 9. 🔴 `disposal_gain_loss`

**Source:** `_compute_disposal_gain_loss()` — queries `AssetDisposal`

**Scope:** Only disposed assets (type=SOLD) whose `disposal_date` falls within this month.

This is **added** (not subtracted) because a gain is positive, a loss is negative (stored as a negative `gain_loss` value on the model).

✅ **Month-specific only.**

---

## Summary Table

| Component | Scope | Accumulates? |
|---|---|---|
| `net_gross_profit` | Invoices confirmed THIS month, returns accepted THIS month | ❌ No |
| `expenses_paid` | `expense_date` in THIS month | ❌ No |
| `recurring_expenses_paid` | `payment_date` in THIS month | ❌ No |
| `gst_paid` | `payment_date` in THIS month | ❌ No |
| `wht_paid` | `payment_date` in THIS month | ❌ No |
| `lost_inventory` | `LostInventoryRecord` **created** in THIS month | ❌ No |
| `found_inventory` | `LostInventoryRecovery` **dated** in THIS month (regardless of loss month) | ❌ No |
| `lost_cash` | `adjustment_date` in THIS month | ❌ No |
| `found_cash` | `adjustment_date` in THIS month | ❌ No |
| `depreciation` | `period == THIS month` | ❌ No |
| `disposal_gain_loss` | `disposal_date` in THIS month | ❌ No |

> [!IMPORTANT]
> **Finalized months are frozen forever.** Once a past month is finalized (you view it after that month ends), the `MonthlyProfit` row is written once and never recomputed. Only the current still-open month is a live, provisional calculation.
