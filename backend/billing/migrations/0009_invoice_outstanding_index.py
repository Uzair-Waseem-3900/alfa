from django.db import migrations


def create_index(apps, schema_editor):
    """
    Partial index backing accounting.selectors.get_ar_aging_rows(), which
    filters confirmed/partial, non-data-entry invoices with
    credit_outstanding > 0 — a small, bounded subset of the table, but
    without this index Postgres would scan every confirmed invoice ever
    created to find them (status alone matches almost all rows).

    PostgreSQL-only (partial indexes with a WHERE clause aren't supported by
    SQLite the same way, and local dev's Invoice table is tiny anyway).
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_invoice_outstanding "
        "ON billing_invoice (status, payment_due_date) "
        "WHERE credit_outstanding > 0 AND is_data_entry = false;"
    )


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS idx_invoice_outstanding;")


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0008_invoiceitemshelfallocation_and_more"),
    ]

    operations = [
        migrations.RunPython(create_index, drop_index),
    ]
