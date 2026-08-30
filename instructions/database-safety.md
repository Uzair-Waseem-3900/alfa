# Database & migration safety (mandatory — not guidance)

Triggered 2026-08-04: `backend/backend/settings.py`'s `DATABASES['default']`
was switched from local SQLite to Postgres/Supabase (env-var driven) earlier
in a session. Every `python manage.py migrate`/`test` run inside that
session's own tool calls kept succeeding against local SQLite (a different
file than what the user's own terminal was pointed at), so the agent had no
signal anything was wrong. When the user later ran `migrate` themselves
against the now-connected Supabase database, it failed with
`InconsistentMigrationHistory` — that database had been created back on
2026-07-20 and only ever received the FIRST round of migrations; entire
apps built since then (`assets`, `backups`, `cash_management`, `profits`,
`recurring_expenses`, `taxes`) had never been applied to it at all. Nobody
had checked `showmigrations` against that target before assuming it was
current. These rules exist so that gap gets caught before it causes a
support fire, not after.

## Hard rules

1. **Never assume "the database" means whatever you last tested against.**
   A Bash/PowerShell tool call and the user's own terminal may not share
   state (different working copies, different `.env`, or — as happened
   here — the user changing `DATABASES['default']` mid-session). Before
   running ANY `migrate`, `makemigrations --check`, or data-touching
   management command, confirm what `DATABASES['default']` currently
   resolves to (read `settings.py`, check which env vars are set) rather
   than assuming it's still SQLite/whatever it was last time.

2. **`git status`/`git diff` on `settings.py` (or any `.env*` file) before
   trusting your last-known DB config.** If either is modified/uncommitted,
   the database target may have changed since you last checked — don't
   silently keep operating on a stale assumption.

3. **Before the FIRST `migrate` against any database you haven't verified
   this session, run `showmigrations` (or query `django_migrations`
   directly) first.** Never run a bare `migrate` as your first move against
   an unfamiliar or newly-connected target — treat every new connection
   (new `.env`, new `DB_HOST`, a freshly-provisioned Supabase/RDS instance)
   as "unknown state until proven otherwise."

4. **A migration-history error (`InconsistentMigrationHistory`,
   unexpected `showmigrations` output, etc.) means STOP and diagnose —
   never guess a fix and run it.** Read the actual `django_migrations` rows
   and the actual table list (`information_schema.tables` on Postgres,
   `sqlite_master` on SQLite) before proposing anything. Report what you
   found in plain terms (which apps/migrations are missing, whether the
   underlying tables/columns already exist or not) and let the user decide
   the fix — do not run `--fake`, `migrate <app> zero`, or any manual
   `django_migrations` edit without their explicit go-ahead for that exact
   command, every time. These commands can silently corrupt a database's
   migration bookkeeping if the diagnosis is wrong.

5. **Check for real data before treating any database as "safe to fix."**
   `SELECT COUNT(*)` on the tables that actually exist, for any target
   before proposing a reset/fake/rebuild fix — a database can be "old" and
   still hold real records. Never assume "this looks like a stale/skeleton
   setup" means "empty" without checking row counts.

6. **Migrations and admin/data-touching commands against anything that
   isn't confirmed-local-throwaway are a "confirm before acting" action**
   under the project's general risk rules (see `CLAUDE.md`) — this applies
   even to commands that are individually reversible (`--fake` can be
   undone in theory, but only if you correctly reconstruct what "correct"
   looked like, which requires the diagnosis step above every time).

7. **Every new environment gets its own migration bootstrap check.** When
   connecting a new backup target, a new deploy environment, or reconnecting
   after a long gap, the correct sequence is: `showmigrations` → diagnose
   any gap → confirm the fix plan with the user → apply → re-run
   `showmigrations` to verify. Never skip straight to `migrate`.
