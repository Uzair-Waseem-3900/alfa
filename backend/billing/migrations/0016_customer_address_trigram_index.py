from django.db import migrations


def create_index(apps, schema_editor):
    """pg_trgm GIN expression index on upper(address): the assistant narrows same-name customers by area
    with search_q(area, "address"). No-op on SQLite (dev). Additive only: no behaviour change."""
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_billing_customer_address_trgm "
        "ON billing_customer USING gin (upper(address) gin_trgm_ops);"
    )


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS idx_billing_customer_address_trgm;")


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0015_invoice_discount"),
    ]

    operations = [
        migrations.RunPython(create_index, drop_index),
    ]
