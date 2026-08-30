from django.db import migrations


def create_index(apps, schema_editor):
    """
    Partial index backing accounting.selectors._compute_opening_balance_equity(),
    which reads the go-live "opening cash" bootstrap rows:

        CashMovement.objects.filter(movement_type="opening_cash", is_deleted=False)

    CashMovement.movement_type is a plain CharField with no index, and none of
    the three indexes on the model (idx_cashmove_active_occurred,
    idx_cashmove_dir_occurred, idx_cashmove_date) can serve that predicate —
    so without this the query sequentially scans the whole table.

    That matters because CashMovement is by design the fastest-growing table
    in the project (one row per payment, expense, supplier payment, tax
    payment, investor movement, asset purchase, forever), while the rows this
    query wants are a handful of bootstrap rows that never change after
    go-live. The cost of reading a permanently-constant number would otherwise
    grow linearly with total business activity, on every live Balance Sheet
    load and every month-rollover catch-up.

    PARTIAL rather than a full index on movement_type: 'opening_cash' is the
    only value ever filtered on in isolation (the Cash Flow Statement's
    .exclude(movement_type="opening_cash") is already bounded by its date
    range and needs nothing extra), and a partial index over a tiny, static
    row set costs essentially nothing to maintain on every insert.

    PostgreSQL-only — same vendor guard as
    purchases.migrations.0014_purchaseorder_outstanding_index.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE INDEX IF NOT EXISTS idx_cashmove_opening_cash "
        "ON cash_flow_cashmovement (movement_type) "
        "WHERE movement_type = 'opening_cash' AND is_deleted = false;"
    )


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS idx_cashmove_opening_cash;")


class Migration(migrations.Migration):

    dependencies = [
        ("cash_flow", "0010_cashflow_total_expenses_count_and_more"),
    ]

    operations = [
        migrations.RunPython(create_index, drop_index),
    ]
