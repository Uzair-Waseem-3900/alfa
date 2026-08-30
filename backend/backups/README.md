# Backups

Four ways to back up the whole system, plus two restore commands. Nothing
is ever kept server-side — local backups stream straight to your browser
as a download; remote backups write directly into a configured remote
Postgres database. The server only ever remembers two things: the last
time a local backup ran, and the last time a remote backup ran
(`BackupFlow`), plus an audit trail of every run (`BackupHistory`).

## Creating a backup

All four are triggered from the **Backups** page in the sidebar (admin/
superuser only), or directly via `POST`:

| What | Endpoint | Produces |
|---|---|---|
| Full, local | `/api/backups/full/local/` | `backup-full-<covers_to>.zip` download |
| Incremental, local | `/api/backups/incremental/local/` | `backup-incremental-<covers_from>-to-<covers_to>.zip` download |
| Full, remote | `/api/backups/full/remote/` | Loaded directly into the configured remote database |
| Incremental, remote | `/api/backups/incremental/remote/` | Loaded directly into the configured remote database |

**Full** = every row in the system, from day one to now.
**Incremental** = only rows changed since the last successful backup of
that *same destination* (local and remote track independent watermarks —
running a local backup never affects when the next remote incremental
starts from, and vice versa).

Each local zip contains exactly **one** `.yaml` file — a standard Django
fixture (the same format `manage.py dumpdata` produces). The filename
itself carries the exact date-time range that file covers; nothing else
is embedded in the zip.

There's no automation here on purpose — nothing runs on a schedule. If you
want regular backups, you have to actually click the buttons (or hit the
endpoints) on whatever cadence you choose.

## Step by step: getting a full local backup

1. Open **Backups** in the sidebar → **Full Backup — Local** → **Run Backup**.
2. Your browser downloads `backup-full-<date>-<time>.zip`.
3. Store that zip somewhere safe, off this server (external drive, your
   own cloud storage — anywhere but here).

## Step by step: getting an incremental local backup

1. Open **Backups** → **Incremental Backup — Local** → **Run Backup**.
2. Downloads `backup-incremental-<from>-to-<to>.zip` — only what changed
   since your last local backup (full or incremental).
3. Keep every incremental file you download, in order — restoring later
   needs the whole chain, not just the latest one.

## Step by step: getting a full or incremental remote backup

1. Make sure `BACKUP_DATABASE` is set in `.env.local` (see **Configuring a
   remote database** below).
2. Open **Backups** → **Full Backup — Remote** or **Incremental Backup —
   Remote** → **Run Backup**.
3. No file downloads — the data is loaded straight into the remote
   database. The response tells you how many rows were backed up, and
   whether the remote's schema had to be migrated first (see below).

Before *any* remote backup runs, the app compares this codebase's applied
migrations against the remote database's. If the remote is behind, it's
migrated automatically first — and that specific run is silently upgraded
from incremental to **full**, regardless of what you clicked. This is a
safety net: a schema change means the old incremental watermark can no
longer be trusted to mean what it used to, so the run re-baselines instead
of risking a gap. Check `schema_migrated` in the response (or the History
page) to see if this happened.

**A full remote backup is an exact mirror — an incremental one isn't.**
Every full backup deletes any remote row that's no longer present in the
source (per model), so the remote never accumulates stale data as long as
you run full backups periodically. Incremental backups only add/update —
they can't detect a row that was deleted between two incrementals (there's
no "changed" event a timestamp filter can see for something that no longer
exists), so a hard-deleted row lingers on the remote until the next full
backup cleans it up. In practice this rarely matters here, since this
project's convention is soft-delete (rows get an `is_deleted` flag, not a
real deletion) — soft deletes ARE just field updates, so they propagate
through incrementals normally. This limitation only applies to genuine
hard deletes, which this codebase avoids by design for anything with
audit/historical relevance.

---

## Restoring a full backup

1. Download a `backup-full-*.zip`, unzip it yourself.
2. Place the single `.yaml` file in:
   ```
   backend/backups/backup_files/full_backup_file/
   ```
3. Run:
   ```
   python manage.py restore_full_backup
   ```
   This migrates whatever database `DATABASES['default']` currently
   points at, then loads the fixture into it.

## Restoring a chain of incremental backups

1. Unzip every `backup-incremental-*.zip` you want to restore.
2. Place all the `.yaml` files together in:
   ```
   backend/backups/backup_files/incremental_backup_files/
   ```
3. (Optional but recommended) Also place the matching full backup's
   `.yaml` in `full_backup_file/` — if it's there, the command verifies
   the incremental chain actually starts right after that full backup,
   not just that the incrementals are consistent among themselves.
4. Run:
   ```
   python manage.py restore_incremental_backups
   ```

The command reads the covered date-range straight out of each filename,
sorts them, and **validates the entire chain for gaps before touching the
database at all.** If everything lines up, it migrates once and loads
every file in order.

### If a gap is found

You'll see exactly where the chain breaks and be prompted:

```
[a]dd the missing file / [p]artial (stop before the gap) / [c]ancel:
```

- **`a` — add**: pauses so you can drop the missing file into the folder,
  then re-scans from scratch when you press Enter.
- **`p` — partial**: proceeds with only the confirmed-continuous prefix
  before the gap. Nothing after the gap is loaded, since its place in the
  chain can't be verified.
- **`c` — cancel**: exits immediately. Since the whole chain is validated
  *before* any migration or data loading happens, cancelling never leaves
  a half-restored database — nothing has been touched yet.

---

## Expected errors, and how to fix them

| Error | What it means | Fix |
|---|---|---|
| `No .yaml file found in .../full_backup_file` | The folder is empty. | Unzip your backup and place the single `.yaml` file there. |
| `Expected exactly one .yaml file in .../full_backup_file, found N` | More than one file is sitting in that folder. | Remove the ones you don't want to restore — exactly one must remain. |
| `No .yaml files found in .../incremental_backup_files` | The incremental folder is empty. | Unzip your incremental backups and place them there. |
| `'<file>' doesn't match the expected incremental backup filename pattern` | A file in the incremental folder was renamed, or isn't actually an incremental backup file. | Restore the original filename exactly as downloaded, or remove the file if it doesn't belong there. |
| `Expected at most one .yaml file in .../full_backup_file, found N` (raised by the incremental command) | More than one full backup file present when the incremental command tried to use it as the chain's anchor. | Keep only the one full backup that actually precedes this incremental chain. |
| `'<file>' ... doesn't match the expected full backup filename pattern` | The full backup file was renamed. | Restore its original filename as downloaded. |
| `Failed to load <file>: ...` | The file isn't a valid fixture, or the database schema doesn't match what the file expects (usually: restoring an old backup against a much newer/older codebase). | Confirm you're running this against the same (or a compatible) version of the codebase that produced the backup, and that the file wasn't corrupted/edited. |
| Gap detected prompt | A file is missing from the middle of the incremental chain. | Use `a` to add the missing file, or `p`/`c` as described above. |
| No remote database configured (`BACKUP_DATABASE` not set) | You tried a remote backup without configuring a target. | See **Configuring a remote database** below. |
| `Remote backup database has migrations not present in this codebase` | The remote's schema has migrations this codebase doesn't know about — an unexpected divergence. | Investigate before retrying — don't back up against a schema you don't understand. This should not happen in normal use (the remote is only ever written to by this app). |

---

## Configuring a remote database

Any Postgres-compatible database works — Supabase, Neon, or a plain
Postgres server you run yourself. Switching providers needs no code
changes, only a connection string.

1. Get your connection string (Supabase/Neon both give you one in their
   dashboard, in standard `postgresql://` form).
2. In `backend/.env` or `.env.local`, set:
   ```
   BACKUP_DATABASE=postgresql://user:password@host:port/dbname?sslmode=require
   ```
3. Restart the Django server. `settings.py` reads this into a `backup_remote`
   database connection automatically — nothing else to configure.
4. Run any remote backup endpoint once to confirm it connects (it'll
   migrate the remote's schema on that first run).

### Cutting over to a remote database as your main database

If you ever need to promote a remote backup target to be the app's actual
live database (disaster recovery, or switching hosting providers):

1. `DATABASES['default']` is currently hardcoded in `settings.py`, not
   read from an env var — edit it directly there to point at that
   database's connection details.
2. Run:
   ```
   python manage.py migrate
   ```
   This applies the schema to whatever `default` now points at — **not**
   `makemigrations`. `makemigrations` only compares this codebase's models
   against the migration files already in the repo; it doesn't know or
   care which database is connected, and won't create anything new here
   since those migration files already exist.
3. Point `BACKUP_DATABASE` at a *different*, fresh target if you want
   remote backups to keep working going forward — you don't want your new
   live database and your backup target to be the same database.
4. That's it. You don't need to manually migrate the new `backup_remote`
   target — the app does that automatically the next time a remote backup
   endpoint runs.
