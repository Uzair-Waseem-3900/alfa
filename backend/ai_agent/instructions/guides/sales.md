# Sales

- "Sales" = real invoices only: confirmed, partially-returned and fully-returned. Drafts and data-entry (imported) invoices are excluded from reports.
- A period filters by the invoice's confirmation date (Asia/Karachi calendar days).
- `billed_total` is the grand total including tax. `cash_collected` is money actually received in that period (it can include payments on older invoices).
- Customer returns reduce revenue and cost: `net_revenue_after_returns` = billed total minus returns accepted in the same window. In a narrow window it can be negative or odd, because a return may belong to an older sale. Say so if it looks strange.
- `gross_profit` = sales minus cost of goods sold (FIFO cost). It is NOT net profit: expenses, depreciation and losses are not deducted. For net profit use profit_report.
- All-time figures come from stored totals; "invoices" in all-time counts non-draft, non-imported invoices.
