from django.db import migrations

# Every icontains-searched column in this app (see instructions/architecture.md
# "Indexed search always"). Product name/code are covered by migration 0010.
#   supplier name/code        : supplier search + supplier_name/supplier_code
#                               filters on orders, payments, returns
#   order_number              : order search
#   supplierpayment reference : payment search (SPY-…)
#   lostinventoryrecord ref   : lost-inventory search (LOSS-…)
#   lostinventoryitem reason  : reason filter on lost-inventory list
_TRIGRAM_TARGETS = [
    ("purchases_supplier",            "name"),
    ("purchases_supplier",            "code"),
    ("purchases_purchaseorder",       "order_number"),
    ("purchases_supplierpayment",     "reference_number"),
    ("purchases_lostinventoryrecord", "reference_number"),
    ("purchases_lostinventoryitem",   "reason"),
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
        ("purchases", "0010_product_trigram_search_indexes"),
    ]

    operations = [
        migrations.RunPython(create_trigram_indexes, drop_trigram_indexes),
    ]
