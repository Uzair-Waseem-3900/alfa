# Payables (money we owe suppliers)

- "We still owe" = the sum of `payable_outstanding` over a supplier's CONFIRMED purchase orders. `total_paid` is what we have paid them so far.
- business_snapshot.we_owe_suppliers is the company-wide stored total.
- suppliers_we_owe lists the biggest payables; supplier_info is for one named supplier.
- Purchase orders in draft are not payables yet.
