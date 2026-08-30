from django.db import migrations

# Every icontains-searched column in this app (see instructions/architecture.md
# "Indexed search always").
#   customer name/code/mobile : customer search + customer_name/customer_code
#                               filters on invoices, payments, returns
#   bill_number               : invoice search
#   payment reference         : payment search (PAY-…)
#   return reference          : returns search (RTN-…)
_TRIGRAM_TARGETS = [
    ("billing_customer", "name"),
    ("billing_customer", "code"),
    ("billing_customer", "mobile"),
    ("billing_invoice",  "bill_number"),
    ("billing_payment",  "reference_number"),
    ("billing_return",   "reference_number"),
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
        ("billing", "0004_alter_invoice_created_at_alter_return_created_at"),
    ]

    operations = [
        migrations.RunPython(create_trigram_indexes, drop_trigram_indexes),
    ]
