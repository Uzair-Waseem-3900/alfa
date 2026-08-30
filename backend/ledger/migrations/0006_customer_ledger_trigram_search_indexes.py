from django.db import migrations

# Every icontains-searched column in this app (see instructions/architecture.md
# "Indexed search always"): the customer ledger list searches customer_name
# and customer_code (snapshot columns on the ledger row itself) — mirrors
# 0003_trigram_search_indexes.py for the supplier side.
_TRIGRAM_TARGETS = [
    ("ledger_customerledger", "customer_name"),
    ("ledger_customerledger", "customer_code"),
]


def create_trigram_indexes(apps, schema_editor):
    """
    Trigram (pg_trgm) GIN expression indexes on upper(col) — matches what
    Django's icontains compiles to on PostgreSQL (UPPER(col) LIKE
    UPPER('%term%')), which no B-tree can serve. No-op on SQLite (dev).
    """
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
        ("ledger", "0005_customerledger_savedcustomerledgerpdf_and_more"),
    ]

    operations = [
        migrations.RunPython(create_trigram_indexes, drop_trigram_indexes),
    ]
