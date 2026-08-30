from django.db import migrations


def rebuild_index(apps, schema_editor):
    """
    Rebuilds idx_purchaseorder_outstanding WITHOUT the
    `is_data_entry = false` predicate — mirror of
    billing.migrations.0010_invoice_outstanding_index_include_data_entry,
    same reasoning.

    A supplier opening balance is a real payable
    (purchases.services.create_opening_balance_order sets
    payable_outstanding=amount, and it feeds
    CashFlow.supplier_payable_outstanding, which the Balance Sheet reports as
    Accounts Payable), so accounting.selectors.get_ap_aging_queryset no longer
    excludes data-entry orders. The index predicate has to stop excluding them
    too, or it can no longer serve that query.

    Note this does NOT pull opening STOCK orders into the index: those never
    call _sync_order_payable, so their payable_outstanding stays 0 and the
    surviving `payable_outstanding > 0` predicate keeps them out — the same
    thing that keeps them out of the report itself.

    PostgreSQL-only, same vendor guard as 0014.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS idx_purchaseorder_outstanding;")
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_purchaseorder_outstanding "
        "ON purchases_purchaseorder (status, confirmed_at) "
        "WHERE payable_outstanding > 0;"
    )


def restore_index(apps, schema_editor):
    """Back to 0014's predicate."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS idx_purchaseorder_outstanding;")
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_purchaseorder_outstanding "
        "ON purchases_purchaseorder (status, confirmed_at) "
        "WHERE payable_outstanding > 0 AND is_data_entry = false;"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0014_purchaseorder_outstanding_index"),
    ]

    operations = [
        migrations.RunPython(rebuild_index, restore_index),
    ]
