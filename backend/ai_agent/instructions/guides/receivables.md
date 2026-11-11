# Receivables (money customers owe us)

- "Still owes / outstanding / balance due" = the sum of `credit_outstanding` over a customer's non-draft invoices. `total_paid` is what they have paid so far; `total_billed` is the invoice grand totals.
- Invoice `payment_status`: unpaid, partial, paid. Invoice `status`: draft, confirmed, partial (partially returned), returned (fully returned).
- Credit tier/score is a per-customer rating based on payment behaviour (overdue invoices lower it). Report it as given; do not explain the formula.
- business_snapshot.customers_owe_us is the company-wide stored total of all customer balances.
- customers_who_owe lists the biggest debtors; customer_info is for one named customer.
