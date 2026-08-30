from django.db import migrations

# Every search_q-searched column in this app (see instructions/architecture.md
# "Indexed search always"): both payment lists search the note field.
_TRIGRAM_TARGETS = [
    ("taxes_taxpayment", "note"),
    ("taxes_whtpayment", "note"),
]


def create_trigram_indexes(apps, schema_editor):
    """
    Trigram (pg_trgm) GIN expression indexes on upper(col) — matches what
    search_q compiles to on PostgreSQL (UPPER(col) LIKE UPPER('%term%')),
    which no B-tree can serve. No-op on SQLite (dev).
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
        ("taxes", "0002_taxflow_total_wht_paid_taxflow_wht_outstanding_and_more"),
    ]

    operations = [
        migrations.RunPython(create_trigram_indexes, drop_trigram_indexes),
    ]
