# Performance Review — Indexing

Analyze every model and recommend proper indexing only where it is actually needed.

Don't blindly add indexes; consider existing indexes, composite indexes, query patterns, read/write trade-offs, and redundancy.

## Search columns

Production runs on Supabase/PostgreSQL. ALL text search goes through
`backend.search.search_q(term, *fields)` — raw `icontains` in app code is
a finding; convert it to `search_q` during the review. Every column
`search_q` targets MUST be backed by a pg_trgm GIN expression index —
`USING gin (upper(<col>) gin_trgm_ops)` — created in a vendor-guarded
migration (no-op on SQLite dev; pattern:
`purchases/migrations/0010_product_trigram_search_indexes.py`).

- `search_q` internally compiles to the UPPER(...) LIKE form that the
  trigram index serves — do not replace it with similarity/fuzzy lookups
  (they change search results and don't run on SQLite).
- A plain `db_index=True` B-tree CANNOT serve a `%term%` match and is not
  an acceptable substitute — flag any unindexed search column as a finding.
- When reviewing an app, enumerate every searched column (including ones
  reached through joins, e.g. `supplier__name`) and check each has its
  trigram index.

## Date filtering

`field__date=`/`__date__gte`/`__date__lte` on a `DateTimeField` is an
automatic finding — it defeats any B-tree index on that column, even when
one exists (`db_index=True` on `confirmed_at`/`accepted_at`/`created_at`
does nothing once `__date` wraps it). This was the single most-repeated
finding across the whole 2026-08 review (present in nearly every app that
filters by a datetime column). Flag it and convert to a half-open range —
see `instructions/architecture.md`'s "Never filter a DateTimeField with
`__date`" rule and `reports.selectors._apply_datetime_range_filter` for the
reusable pattern. A plain `DateField` (`expense_date`, `payment_date`) is
already fine as-is — this only applies to `DateTimeField` columns.

Also check: does the date/timestamp column being filtered/ordered by
actually have an index at all? `AuditMixin`'s `created_at` is unindexed by
default — several apps override it per-model where a report/selector
actually uses it (`PurchaseOrder`, `PurchaseReturn`, `LostInventoryRecord`,
`RecurringExpenseAssignment.assigned_at`, `BackupHistory.created_at`).
Missing that override on a newly-filtered column is a finding too.
