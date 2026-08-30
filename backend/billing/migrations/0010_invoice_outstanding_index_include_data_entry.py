from django.db import migrations


def rebuild_index(apps, schema_editor):
    """
    Rebuilds idx_invoice_outstanding WITHOUT the `is_data_entry = false`
    predicate.

    accounting.selectors.get_ar_aging_queryset used to exclude data-entry
    invoices, and 0009's partial index matched that exclusion. But a customer
    opening balance IS a real receivable — a CONFIRMED invoice with
    credit_outstanding set, feeding CashFlow.customer_outstanding, which the
    Balance Sheet reports as Accounts Receivable. Leaving them out meant the
    A/R Aging report could never reconcile with the Balance Sheet and real
    money owed was missing from the collections list.

    Now the selector no longer filters on is_data_entry, so a partial index
    that still carries `AND is_data_entry = false` in its predicate can NOT
    serve the query — Postgres would fall back to a sequential scan on
    billing_invoice. Dropping that clause from the predicate keeps the index
    matching the query it exists for.

    Still partial on `credit_outstanding > 0`: that is the whole point — the
    index covers only unpaid invoices, which is a small and self-limiting
    slice of the table, not every invoice ever raised.

    PostgreSQL-only, same vendor guard as 0009.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS idx_invoice_outstanding;")
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoice_outstanding "
        "ON billing_invoice (status, payment_due_date) "
        "WHERE credit_outstanding > 0;"
    )


def restore_index(apps, schema_editor):
    """Back to 0009's predicate."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS idx_invoice_outstanding;")
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoice_outstanding "
        "ON billing_invoice (status, payment_due_date) "
        "WHERE credit_outstanding > 0 AND is_data_entry = false;"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0009_invoice_outstanding_index"),
    ]

    operations = [
        migrations.RunPython(rebuild_index, restore_index),
    ]
