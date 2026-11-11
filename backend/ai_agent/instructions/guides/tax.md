# Tax

- Sales tax: `total_output_tax_collected` (charged on sales) minus `total_input_tax_paid` (paid on purchases) = `net_sales_tax_payable`; `sales_tax_outstanding` is what remains unpaid to the tax authority after payments (`total_sales_tax_paid`).
- WHT (withholding tax): `total_wht_withheld_from_suppliers` is deducted from supplier payments and owed to the authority; `total_wht_withheld_by_customers` is deducted from us by customers; `wht_outstanding` is the part not yet deposited.
- These are all-time running positions, not per-period filings. Computed figures are not tax advice; recommend confirming with the accountant before filing.
