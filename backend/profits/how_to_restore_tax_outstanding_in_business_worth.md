# How to Restore Sales Tax Outstanding / WHT Outstanding in Business Worth

> **Context (2026-07-29):** On explicit request, **Sales Tax (GST) Outstanding** and **WHT Outstanding** were removed from the Total Business Worth calculation and from the Business Worth page's display — but only by **commenting out** the relevant lines, never deleting them. Nothing about *what these fields are* or *how they're computed* (`TaxFlow.sales_tax_outstanding` / `TaxFlow.wht_outstanding`) changed — they're still live, still accurate, just no longer subtracted or shown here. This note is the exact, minimal procedure to reverse that — uncomment four spots across two files.

For the full original reasoning on why these two were liabilities in the first place, see `backend/profits/business_wealth.md` §3 (unchanged — still accurate, describes the pre-2026-07-29 behavior).

---

## What changed, and exactly how to undo it

### 1. Backend — `backend/profits/selectors.py`, inside `get_business_worth()`

Currently:
```python
    # 2026-07-29: Sales Tax Outstanding and WHT Outstanding temporarily
    # excluded from the total per explicit request — see
    # profits/how_to_restore_tax_outstanding_in_business_worth.md to reverse.
    total_business_worth = (
        cash_in_hand
        + inventory_value
        + assets_current_worth
        + customer_outstanding
        - supplier_payable_outstanding
        # - sales_tax_outstanding
        # - wht_outstanding
        - recurring_expense_pending
    )
```

**To reverse:** uncomment the two lines (`- sales_tax_outstanding` and `- wht_outstanding`), and delete the three-line dated comment above it (or leave it — it's harmless once the code below it no longer matches what it describes, but removing it keeps the file clean). Result should read exactly as it did before 2026-07-29:
```python
    total_business_worth = (
        cash_in_hand
        + inventory_value
        + assets_current_worth
        + customer_outstanding
        - supplier_payable_outstanding
        - sales_tax_outstanding
        - wht_outstanding
        - recurring_expense_pending
    )
```

Nothing else in this function changed — the dict returned at the bottom (`return {...}`) always kept `sales_tax_outstanding`/`wht_outstanding` as live keys, so the API response never stopped including them; only the arithmetic and the frontend display were affected.

### 2. Frontend — `frontend/src/pages/profits/BusinessWorthPage.jsx`, chart data (`worthBreakdownData`)

Currently:
```jsx
            { name: 'Supplier Payable', value: -parseFloat(data.supplier_payable_outstanding), type: 'liability' },
            // Sales Tax Outstanding and WHT Outstanding temporarily excluded — see
            // backend/profits/how_to_restore_tax_outstanding_in_business_worth.md to reverse.
            // { name: 'Sales Tax Outstanding', value: -parseFloat(data.sales_tax_outstanding), type: 'liability' },
            // { name: 'WHT Outstanding', value: -parseFloat(data.wht_outstanding), type: 'liability' },
            { name: 'Recurring Exp. Pending', value: -parseFloat(data.recurring_expense_pending), type: 'liability' },
```

**To reverse:** delete the two-line comment and uncomment the two `{ name: ... }` entries.

### 3. Frontend — same file, "Liabilities (subtracted)" `StatBox` grid

Currently:
```jsx
                            <StatBox label="Supplier Payable" value={data.supplier_payable_outstanding} tone="red" sign="−" subtitle="Owed to suppliers (payable)" />
                            {/* Sales Tax Outstanding and WHT Outstanding temporarily excluded — see
                                backend/profits/how_to_restore_tax_outstanding_in_business_worth.md to reverse. */}
                            {/* <StatBox label="Sales Tax Outstanding" value={data.sales_tax_outstanding} tone="red" sign="−" subtitle="GST still owed to FBR" /> */}
                            {/* <StatBox label="WHT Outstanding" value={data.wht_outstanding} tone="red" sign="−" subtitle="Withheld from suppliers, not deposited" /> */}
                            <StatBox label="Recurring Exp. Pending" value={data.recurring_expense_pending} tone="red" sign="−" subtitle="Assigned dues, not yet paid" />
```

**To reverse:** delete the JSX comment block and uncomment the two `<StatBox ... />` lines.

---

## Verification after reversing

1. `python manage.py check` (backend).
2. Re-run the same live check used when this was first applied:
   ```python
   from profits.selectors import get_business_worth
   w = get_business_worth()
   print(w["sales_tax_outstanding"], w["wht_outstanding"], w["total_business_worth"])
   ```
   Confirm `total_business_worth` now equals what it was **minus** `sales_tax_outstanding` and `wht_outstanding` (i.e. they're subtracted again).
3. Test the actual view via `APIRequestFactory` (`profits.views.BusinessWorthView`) — confirm 200 and the same total.
4. `npm run build` (frontend) and visually confirm both the bar chart and the "Liabilities (subtracted)" grid show Sales Tax Outstanding / WHT Outstanding again.
5. No migration needed either direction — nothing about the database schema changed, only which already-existing fields are read into the total.

---

## Prompt for another AI

```
You are working in the AlphaPK Django ERP backend/frontend. Sales Tax
Outstanding and WHT Outstanding were previously commented OUT of the Total
Business Worth calculation and its display, per
backend/profits/how_to_restore_tax_outstanding_in_business_worth.md — read
that file first, it has the exact before/after code for all 3 spots.

Task: reverse this — restore both fields as subtracted liabilities in the
total AND as visible line items on the Business Worth page, exactly as
documented in that file.

Requirements:
1. Uncomment (don't rewrite) the exact lines identified in the md file:
   - backend/profits/selectors.py — the two `- sales_tax_outstanding` /
     `- wht_outstanding` lines inside get_business_worth()'s
     total_business_worth formula.
   - frontend/src/pages/profits/BusinessWorthPage.jsx — the two entries in
     worthBreakdownData, and the two <StatBox> lines in the "Liabilities
     (subtracted)" grid.
2. Remove the dated comment blocks that explained the temporary exclusion
   (they'll no longer be accurate once reversed).
3. Do not change anything else — not the dict/serializer shape, not
   TaxFlow, not any other component of the business worth calculation.
4. Verify with the exact steps in the "Verification after reversing"
   section of the md file, and report the before/after total_business_worth
   values.
```
