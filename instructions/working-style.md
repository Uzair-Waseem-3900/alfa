# How this user likes to work — read every session

- **Never test against production DB.** If `DATABASES['default']` points at production, use a local-only settings override (e.g. `backend.settings_local_test`, swap `DATABASES` back to SQLite) for `manage.py test`, then delete the override file after.
- **Always background test runs.** Never block the conversation on a test command. Read the FULL failure output before deciding root cause, not a truncated tail.
- **Verify empirically, not theoretically.** Run real queries/requests (`RequestFactory`, `CaptureQueriesContext`) against real data before claiming a bug's cause or a fix's effect. If asked for a timing number, measure it.
- **Root cause before fix.** Explain *why* a bug happens, traced to real code, before presenting the fix plan.
- **Plan first, always** — and when the user questions a design choice, treat it as "change this," not "explain this again." Confirm, then fix.
- **Performance is a hard requirement** on new report/list/dashboard work — "under 200ms," "O(1) or O(25) page size" — design and verify against it, don't estimate. Check for duplicate computation (same query run twice per request) before reaching for indexes.
- **Independent audits for risky/new backend work** — run one proactively (`instructions/performance-review-*.md`), don't wait to be asked.
- **Background agents for parallel/audit work** — scope them tightly and precisely (exact files, exact checks, "do it yourself, don't delegate further") rather than vague fast-and-loose prompts; precision is what keeps it fast *and* correct.
- **User drives git.** Prepare and verify code; they commit/push themselves unless told otherwise.
- **Direct, terse prompts, mid-turn interruptions are real steering** — act on them immediately, don't finish the prior plan first. Once done, summarize tight — no restating the session.
