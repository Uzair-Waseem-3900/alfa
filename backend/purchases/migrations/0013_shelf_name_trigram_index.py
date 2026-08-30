from django.db import migrations

# Shelf.name is searched via search_q() in get_all_shelves() — every
# search_q-targeted column needs a matching trigram index (see
# instructions/architecture.md "Indexed search always"). Missed in
# migration 0011's sweep since Shelf search was added later, with the
# shelf-stock feature.
_TRIGRAM_TARGETS = [
    ("purchases_shelf", "name"),
]


def create_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")
    for table, column in _TRIGRAM_TARGETS:
        schema_editor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_{column}_trgm "
            f"ON {table} USING gin (upper({column}) gin_trgm_ops);"
        )


def drop_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, column in _TRIGRAM_TARGETS:
        schema_editor.execute(f"DROP INDEX IF EXISTS idx_{table}_{column}_trgm;")


class Migration(migrations.Migration):

    dependencies = [
        ("purchases", "0012_remove_product_shelf_purchaseitemshelfallocation_and_more"),
    ]

    operations = [
        migrations.RunPython(create_trigram_indexes, drop_trigram_indexes),
    ]
