# AI assistant — v2 backlog (everything deliberately left open in v1)

Written at the end of v1. Nothing here blocks v1; each item says what is wrong, where, why it matters, and how to fix it. Read `instructions/agent_instructions.md` first (the rules these fixes must respect). Evidence comes from two independent code audits (read-only reviews) plus live testing.

Status legend: **OPEN** (not done) · **PARTIAL** (mitigated, full fix open) · **OWNER-DECLINED** (don't redo unless asked) · **ACCEPTED** (known, tolerated).

---

## A. Four findings that need a product decision (invoice write tools)

### A1. An edit wipes the shelf choices on a draft — PARTIAL
- **Where:** `billing/services.py` `update_invoice_items` does `invoice.items.all().delete()` and recreates the lines; `InvoiceItemShelfAllocation` rows hang off those lines and are deleted with them. `ai_agent/services/invoicing.py` `update_draft` re-sends all lines.
- **Effect:** changing one field through the assistant silently erases shelf allocations a person already made; the draft can't be confirmed until they are redone. (The Billing page behaves the same, but a human is looking at the form there.)
- **Done in v1:** the summary adds a heads-up ("shelf choices ... cleared ... set them again in the Billing page"), test in `tests/test_invoice_hardening.py::HeadsUpTests`.
- **v2 options:** (A) keep the heads-up; (B) **refuse** to edit a draft that has shelf choices and tell the user to edit it in Billing. Recommended: B.
- **How:** in `update_draft`, `had_shelf_choices` is already computed from the prefetched items (0 extra queries) — raise `ToolInputError` instead of building the note; update `HeadsUpTests` and the `invoices.md` guide.

### A2. Person and assistant editing the same draft at once — OPEN (billing change)
- **Where:** `billing/services.py` `update_invoice_items` / `delete_invoice` read the invoice without `select_for_update()` and finish with `invoice.save(update_fields=[payment_type, advance_amount, ...])`.
- **Effect:** the assistant reads the draft, then needs seconds (about 100 ms per query on a remote DB) before writing. If someone changes the draft in the Billing page in that window (e.g. adds an advance), the assistant's save can overwrite `advance_amount`/`payment_type` from its stale copy and desync the invoice from its Payment/cash rows. Two assistant edits of the same draft can also overlap. The race exists in billing today; the assistant widens the window.
- **v2 options:** (A) leave it; (B) lock the invoice row inside the billing services (also protects the Billing page) — **needs explicit owner approval, it is a billing change**; (C) agent-layer only, no billing change: inside the write transaction `Invoice.objects.select_for_update().get(pk=...)`, compare `updated_at`/advance fields with what was read, and refuse with "the draft changed while I was preparing the edit — please repeat". Recommended: B, or C if billing must stay untouched.
- **Tests to add:** two edits racing (use `threading` + `TransactionTestCase`; note SQLite ignores row locks, so also verify on Postgres), edit vs. advance added mid-flight.

### A3. Prompt injection can aim the tools at any draft — OPEN
- **Where:** `update_draft` / `discard_draft` accept any `bill_number` (owner decision: "any draft by bill number").
- **Effect:** customer/product names and tool results are text the model reads. A hostile name like "discard BILL-2026-0007" could make the agent soft-discard or rewrite drafts the user never mentioned (up to the write budget; drafts with an advance and confirmed invoices are protected).
- **v2 fix (recommended):** a provenance check in code. The bill number must appear in (1) a user message of this chat (regex `BILL-\d{4}-\d{4}`, case-insensitive), or (2) an `AgentAction` of this chat. Also worth adding: `customer_id`/`product_id` must have been returned by a `find_*` tool in this run (blocks hallucinated ids). Keep the "any draft by bill number" feature: the user just types the number.
- **How:** `services/invoicing.py` helper `_bill_is_authorised(chat_id, bill)`; query `ChatItem(kind="user")` of the chat (index `(chat, kind, id)`) plus `AgentAction` of the chat; keep it to 2 small indexed queries. For ids, add a mutable `seen_ids` set on `AgentContext` filled by the `find_*` tools.
- **Tests to add:** a bill number that appears only inside a customer name is refused; typed by the user is allowed; created earlier in the chat is allowed.

### A4. No cap on discounts or due dates — PARTIAL
- **Where:** `_line_discount` allows any value from a surcharge of the full price to a 100% discount (a line may be free or double-priced; surcharges are allowed by owner decision); `_due_date` has no upper bound; gst/wht allow up to 100.
- **Done in v1:** a free line gets a heads-up in the summary.
- **v2 fix:** settings such as `AGENT_MAX_LINE_DISCOUNT_PERCENT` (owner picks, e.g. 50) and `AGENT_MAX_DUE_DAYS` (e.g. 365), enforced in `_line_discount` / `_due_date` with plain-language refusals; consider a business-chosen cap for GST/WHT too. These are assistant-side rules only (billing's own "invoice discount ≤ profit" check stays).
- **Tests to add:** over-cap discount and far-future due date refused, at-cap allowed.

---

## B. Other open items

| # | Item | Where / evidence | Status | v2 fix |
|---|---|---|---|---|
| B1 | Write tools are slow because billing itself is: create ≈ 14 + 6n queries, update ≈ 17 + 5m (all lines), discard ≈ 11, `show_draft_invoice` 3 | `billing/services.py` per-line lookups and `_invoice_qs` prefetch; measured by reading, not by timing | ACCEPTED (pre-existing billing N+1) | Optimise billing's `create_invoice`/`update_invoice_items` (bulk product + stock lookups). Needs separate approval (billing change). |
| B2 | SSE: every open stream holds a DB connection (auth + `aexists` each 15 s) and a Redis client; no per-user stream cap | `ai_agent/views.py` `run_stream`, `services/streaming.py` | OPEN | Close DB connections right after setup; make the idle check cheap (Redis flag or finished marker); cap concurrent streams per user (e.g. 3). |
| B3 | Idempotency key is a hash of exact arguments and is order-sensitive | `_args_hash` | PARTIAL: the runner never auto-retries after a write, and errors name the bills | Canonicalise (sort lines by product id, normalise defaults) or add a semantic key (run, tool, customer, sorted product+qty). |
| B4 | A legitimate repeat inside one question (edit A, edit B, edit A again) is treated as a duplicate and skipped | `_repeat_of` | ACCEPTED (rare) | Include the pre-update state in the hash. |
| B5 | A tool thread outlives `asyncio.timeout`: a write can still commit after the run is marked failed | `services/runner.py`, `my_tool/base.py` | ACCEPTED | Pass a deadline into write tools; or run write tools with cooperative cancellation. The error message already names changed bills. |
| B6 | Concurrency tests only run on SQLite (row locks are ignored there) | all tests | OPEN | Run the race tests (budget lock, idempotency race, A2) against a local Postgres. |
| B7 | `find_customers` takes the first 9 matches unordered; with ≥ 9 substring matches an exact name/code may not be among them (safe failure: reports "multiple") | `selectors/invoicing.py` | OPEN | Add a selector for exact name/code lookup (no raw text lookups in app code — `architecture.md`); fall back to substring. |
| B8 | Billing's validation messages reach the model verbatim, e.g. "exceeds this invoice's gross profit Rs X" and physical stock numbers (a cost-basis oracle for an injected prompt; admin-only, and `profit_report` already shows profit) | `explain()` in `services/invoicing.py` | ACCEPTED | Replace the profit-bearing message with a generic one. |
| B9 | Abandoned or injected drafts keep reserving stock for other drafts until discarded | draft reservation in billing `_validate_stock` | ACCEPTED | A periodic listing/cleanup of agent drafts older than N days (needs a retention policy decision). |
| B10 | Tool schemas cost ≈ 4,000 tokens per model call (20 tools) | `my_tool/*` | OPEN | Trim duplicated sentences (the "show summary_markdown exactly" rule repeats in 3 descriptions), drop `show_draft_invoice` if unused, shrink the nested line schema. About 300–500 tokens saved. |
| B11 | `business_worth` ≈ 6 queries; `sales_summary` all-time ≈ 8; `customer_info`/`supplier_info` ≈ 4 | measured on the local DB (`customer_info` is capped at 3 detailed matches) | OWNER-DECLINED (business_worth), OPEN (sales_summary) | `business_worth`: one narrow query gives the identical inventory value (prototype matched to 0.0000, 1 query instead of 2). `sales_summary` all-time: a single selector fetching `CashFlow` once. Both touch other apps → separate approval. |
| B12 | `customers_who_owe` / `suppliers_we_owe` are annotated Sum + HAVING over all invoices/orders; Postgres plan never checked (owner: test locally only) | `billing/selectors.py`, `purchases/selectors.py` | OPEN | `EXPLAIN ANALYZE` on a Postgres copy with realistic rows; fix in the existing selector if slow. |
| B13 | `expenses_summary` all-time does a full-table SUM/COUNT although a stored total exists (`CashFlow.total_expenses_amount`) | `cash_flow/selectors.py` | OPEN | Use the stored total when there is no search/date filter. |
| B14 | Redundant indexes: `ChatItem` has three prefixes on `chat`; `Chat` has a standalone `is_deleted` index plus the FK index | `models.py` | OPEN (optional) | Migration dropping `idx_chatitem_chat_id` and the `is_deleted` index; optional partial index `(chat, id) WHERE kind IN ('user','assistant')` for the history query. |
| B15 | Chat/Item/Run/AgentAction rows grow forever (soft-deleted chats too) | `models.py` | OWNER-DECLINED for now | `prune_agent_data` command: hard-delete chats soft-deleted > 30 days, finished runs > 14 days, tool call/output items > 90 days (keep questions and answers); chunked deletes, `--dry-run`, plus indexes on `ChatItem(kind, created_at)`, `ChatRun(finished_at)`, `Chat(deleted_at)`. Design was agreed in chat. |
| B16 | The `agent` throttle (20/min) also applies to reading history, not only sending | `views.py` `ChatMessagesView` | OWNER-DECLINED | Apply the scoped throttle to POST only (`get_throttles`). |
| B17 | `get_items` window edge case | `services/session.py` | FIXED in v1 (extends back to the turn's user message, ≤5×) | — |
| B18 | Celery `solo` pool runs one question at a time; the Celery hard time limit isn't enforced by it | settings `CELERY_WORKER_POOL`, deployment | OPEN (owner manages deployment) | Production: threads/prefork pool with concurrency 2–4 on queue `agent`, ASGI server (`uvicorn` workers) for SSE. |
| B19 | Gemini free tier is tiny (flash: 20 requests/day per model+project, one question costs 2–3); weaker models skip guides or tool-call less reliably | live testing | ACCEPTED (dev) | Paid quota or another model for production; re-run the live checks (`agent_instructions.md` → Testing) on whatever model is chosen. |
| B20 | Gemini streams are cut off about 1 time in 12 (retried once, costs ~3–5 s) | `config/gemini_compat.py` | ACCEPTED | If it stays frequent, fetch whole answers (no live token streaming) — trade-off discussed with the owner (Option 3). |

---

## C. Product / UI ideas not built in v1
- A styled **draft-invoice card** in the chat (needs the structured data stored with the message); v1 shows a markdown summary + link.
- A **stop/cancel** button for a running answer (owner: not for v1).
- **Resume an answer after a page refresh** mid-stream (the stream can be replayed via `Last-Event-ID`; the UI doesn't reattach).
- Suggested prompt for invoices on the empty chat screen; chat search; per-chat export.
- Advance payments, confirming invoices and creating customers through the assistant (all deliberately excluded; revisit only with an explicit safety design — an advance moves cash even on a draft).
- Pending housekeeping: run `python manage.py migrate ai_agent` for `0002_agentaction` on every real database.

---

## D. Already fixed in v1 (for reference, don't redo)
Retry after a write no longer duplicates (runner stops retrying once a run wrote; errors name the bills) · write budget re-counted under a lock + per-run cap · `find_product_for_invoice` 25 → 1–3 queries, products loaded in bulk on writes · names markdown-escaped and the chat renderer drops images and non-https/non-relative links · discard no longer reports success on a real `IntegrityError` · replay of a discarded draft says so · update sizes checked up front · NaN/inf rejected, GST/WHT rounded explicitly · unknown arguments (price, advance, status) are refused, not ignored · stream cut-off retry with rollback + `reset` · empty-completion retry · tool-call index shim · model client closed per run · `find_invoices` uses a lean selector (2 queries instead of 4).

## Bulk invoices: audit items left for the owner / v2
Found by the independent audit of the bulk feature (the rest were fixed: one draft per bulk row, lost queued tasks re-queued, skip never hides a draft, batch status under a row lock, Redis blip at row start, cancelled-batch answers refused, `unit_rate` floor and note, one active run per row, stream MAXLEN, admin).
- **E1 (decision):** in bulk, ids from a `match: multiple` lookup still unlock a write (the model may pick one with nobody to ask). Recommended: bulk records only `unique` ids; multiples force `needs_attention`.
- **E2 (decision):** a single PARTIAL name match counts as unique (e.g. "Ali" -> only "Alizeh Traders" inside the chosen link name). Recommended for bulk: accept only an exact name/code match, otherwise ask with that candidate as the option.
- **E3 (decision):** a double-submitted batch (double click / retry after a timeout) creates two batches and two drafts per row. Options: client idempotency key, or refuse an identical prompt set from the same user within a few minutes.
- **E4 (decision):** no cap on queued rows per user (60 creates/min x 100 rows). Suggest refusing a new batch while the user already has more than N active rows.
- **E5 (decision):** `qty@0` is treated as "rate not given" (list price), so a "free" line is priced at list. Decide whether `@0` should mean free or be a question.
- E6: a Gemini 429 ends the row at once (no backoff) and spends an attempt.
- E7: API-side transitions (answer/skip/retry/cancel) publish no SSE event, so a second open tab stays stale until it reloads.
- E8: no retention for `ChatRun` / `AgentAction` rows of bulk attempts; the batch detail GET returns every prompt (<= 100 x 2,000 chars) on each poll.
- E9: customer address and the stored question/options flow back into the next run's prompt (data, never instructions, but a hijack could only ever produce a draft, and E1/E2 widen it).
