from django.db import migrations


def create_index(apps, schema_editor):
    """
    Partial index backing accounting.selectors.get_ap_aging_rows(), which
    filters confirmed, non-data-entry purchase orders with
    payable_outstanding > 0 — same reasoning as
    billing.migrations.0009_invoice_outstanding_index.

    PostgreSQL-only.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_purchaseorder_outstanding "
        "ON purchases_purchaseorder (status, confirmed_at) "
        "WHERE payable_outstanding > 0 AND is_data_entry = false;"
    )


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS idx_purchaseorder_outstanding;")


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0013_shelf_name_trigram_index"),
    ]

    operations = [
        migrations.RunPython(create_index, drop_index),
    ]
