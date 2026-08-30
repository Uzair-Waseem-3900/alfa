from django.db import migrations


def create_trigram_indexes(apps, schema_editor):
    """
    Trigram (pg_trgm) GIN indexes so icontains product search (inventory,
    products, rates pages all search product name/code) is index-backed
    instead of a full table scan. A plain B-tree cannot serve a
    '%term%' match, which is why these are expression GIN indexes.

    Indexed on upper(...) to match exactly what Django's icontains compiles
    to on PostgreSQL: UPPER(col) LIKE UPPER('%term%').

    PostgreSQL-only: on SQLite (local dev/tests) this is a no-op — the
    tables there are small enough that the scan is negligible, and SQLite
    has no trigram support.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_name_trgm "
        "ON purchases_product USING gin (upper(name) gin_trgm_ops);"
    )
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_product_code_trgm "
        "ON purchases_product USING gin (upper(code) gin_trgm_ops);"
    )


def drop_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS idx_product_name_trgm;")
    schema_editor.execute("DROP INDEX IF EXISTS idx_product_code_trgm;")


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0009_inventorystatsflow_alter_inventory_quantity_and_more"),
    ]

    operations = [
        migrations.RunPython(create_trigram_indexes, drop_trigram_indexes),
    ]
