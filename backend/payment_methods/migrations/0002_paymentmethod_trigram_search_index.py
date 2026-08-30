from django.db import migrations


def create_trigram_indexes(apps, schema_editor):
    """
    Trigram (pg_trgm) GIN index so icontains PaymentMethod name search is
    index-backed instead of a full table scan. PostgreSQL-only: no-op on
    SQLite (local dev/tests), see purchases/migrations/0010 for the same
    pattern.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_paymentmethod_name_trgm "
        "ON payment_methods_paymentmethod USING gin (upper(name) gin_trgm_ops);"
    )


def drop_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS idx_paymentmethod_name_trgm;")


class Migration(migrations.Migration):

    dependencies = [
        ("payment_methods", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_trigram_indexes, drop_trigram_indexes),
    ]
