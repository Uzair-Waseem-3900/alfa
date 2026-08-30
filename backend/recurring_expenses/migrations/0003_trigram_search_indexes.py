from django.db import migrations

# Every search_q-searched column in this app (see instructions/architecture.md
# "Indexed search always"). Explicit short index names — the usual
# idx_<table>_<column>_trgm convention would exceed PostgreSQL's 63-char
# identifier limit for these table names.
_TRIGRAM_TARGETS = [
    ("recurring_expenses_recurringexpensecategory",   "name",          "idx_rec_exp_category_name_trgm"),
    ("recurring_expenses_recurringexpense",           "name",          "idx_rec_exp_name_trgm"),
    ("recurring_expenses_recurringexpenseassignment", "name_snapshot", "idx_rec_exp_assign_name_trgm"),
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
    for table, column, index_name in _TRIGRAM_TARGETS:
        schema_editor.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON {table} USING gin (upper({column}) gin_trgm_ops);"
        )


def drop_trigram_indexes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for _table, _column, index_name in _TRIGRAM_TARGETS:
        schema_editor.execute(f"DROP INDEX IF EXISTS {index_name};")


class Migration(migrations.Migration):

    dependencies = [
        ("recurring_expenses", "0002_remove_recurringexpenseassignment_unique_recurring_expense_assignment_per_period_and_more"),
    ]

    operations = [
        migrations.RunPython(create_trigram_indexes, drop_trigram_indexes),
    ]
