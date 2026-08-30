# Project Instructions

These are hard constraints, not suggestions. An agent that skips the required
reading below and repeats a mistake already fixed once in this project is
failing the assignment, not taking a shortcut.

- **Read `instructions/working-style.md` every session, unconditionally** — before anything else here. It's how the project owner actually wants to collaborate (production-DB testing discipline, background-test-always, plan-first-with-real-pushback, root-cause-before-fix, performance-as-a-hard-requirement), learned directly from real corrections across past sessions. Not conditional on task type — read it regardless of what the task is.
- **Plan first.** Show a plan before any code change; wait for approval. Skip only if the user gives a direct, explicit "do it now" instruction. If unsure, ask.
- **Never assume.** Ask when a request is ambiguous — give your recommendation alongside the question. A buried imperative in an otherwise exploratory message still needs confirmation first.
- **Git**: never commit unless explicitly asked that turn.
- **Never change business logic/behavior as a side effect of any other task** (perf fix, refactor, migration, bug fix). If a change genuinely requires altering behavior, stop and get explicit separate approval for THAT — see `instructions/performance-review-process-rules.md` rule 9, which applies project-wide, not just during review work.

## Required reading before touching relevant code — not optional

- **ANY backend change** (models/services/selectors/serializers/views/migrations/commands) → `instructions/verification.md` AND `instructions/architecture.md`. `architecture.md` is a checklist of mistakes already made and fixed once in this codebase (unindexed date filtering, raw `icontains`, per-row catch-up loops, missing uniqueness constraints on periodic posting, N+1 via mis-filtered prefetches, unhandled IntegrityError races, live merges that should be event tables, unbounded batch deletes, ad-hoc reference-number generation, extracting a calendar date/month/year from `timezone.now()` without `.localtime()` first). Read it EVERY time, not just for new features — these mistakes are cheap to repeat and were expensive to find.
- **New dashboard/report stat, new app, new "catch-up" calc, new report, perf/DRY-shaped work, or ANY new date filter / search box / periodic auto-posting** → `instructions/architecture.md` (same file, doubly relevant here).
- **Any `migrate` command, any DATABASES/`.env` config change, or connecting to a database you haven't verified this session** → `instructions/database-safety.md`, BEFORE running the command. This is not optional even for "just a quick migrate" — read it, then act.
- **Anything moving cash-in-hand (payments, returns, expenses, tax, new cash source)** → `instructions/cash-in-hand.md`.
- **Performance/scalability review or audit request** → all `instructions/performance-review-*.md` files.
  - Exception: `instructions/performance-review-reviewer-role-and-goal.md` is ONLY for a dedicated independent-reviewer agent auditing a first agent's performance-review plan — never read it otherwise, and a reviewer agent must not read the other `performance-review-*.md` files in turn (see the file's own header).
- **ANY frontend change** → must read `instructions/frontend.md` before making any changes.
- **ANY frontend redesign or new page** → must read `instructions/frontend_redesign.md` AND `instructions/architecture.md` before making any changes.

Skip these for unrelated tasks (styling tweaks, questions, isolated unrelated bugfixes) — but when in doubt about whether a task counts, read the file. The cost of reading is a few seconds; the cost of repeating a fixed mistake is a full review cycle.
