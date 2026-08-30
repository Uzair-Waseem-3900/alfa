import re
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

INCREMENTAL_DIR = Path(settings.BASE_DIR) / "backups" / "backup_files" / "incremental_backup_files"
FULL_DIR = Path(settings.BASE_DIR) / "backups" / "backup_files" / "full_backup_file"

STAMP_FORMAT = "%Y%m%d-%H%M%S"
INCREMENTAL_RE = re.compile(r"^backup-incremental-(\d{8}-\d{6})-to-(\d{8}-\d{6})\.yaml$")
FULL_RE = re.compile(r"^backup-full-(\d{8}-\d{6})\.yaml$")


def _parse_stamp(stamp: str) -> datetime:
    return datetime.strptime(stamp, STAMP_FORMAT)


class Command(BaseCommand):
    help = (
        "Restores a chain of incremental backups. Place all .yaml incremental "
        "fixture files (unzipped) in backend/backups/backup_files/incremental_backup_files/, "
        "then run this command. The entire chain is validated for gaps BEFORE "
        "any database change is made — cancelling at the gap prompt changes nothing."
    )

    def handle(self, *args, **options):
        while True:
            files = self._collect_files()
            anchor = self._get_full_backup_anchor()
            valid_prefix, gap = self._validate_chain(files, anchor)

            if gap is None:
                entries = valid_prefix
                break

            choice = self._prompt_gap(gap)
            if choice == "a":
                input(
                    f"Place the missing file (covering {gap['expected'].strftime(STAMP_FORMAT)} onward) "
                    f"in {INCREMENTAL_DIR}, then press Enter to re-scan..."
                )
                continue
            elif choice == "p":
                entries = valid_prefix
                break
            else:  # cancel
                self.stdout.write(self.style.WARNING("Cancelled — nothing was changed."))
                return

        if not entries:
            self.stdout.write("Nothing to restore (no valid files before the first gap).")
            return

        self.stdout.write(f"Restoring {len(entries)} incremental file(s) in order:")
        for path, covers_from, covers_to in entries:
            self.stdout.write(f"  - {path.name}")

        self.stdout.write("Applying migrations to the current database...")
        call_command("migrate", interactive=False, verbosity=1)

        # One transaction across the WHOLE chain — if any file in the
        # middle fails, everything loaded so far in this run rolls back
        # too, instead of leaving a half-restored database that only the
        # files-before-the-failure actually landed in.
        try:
            with transaction.atomic():
                for path, covers_from, covers_to in entries:
                    self.stdout.write(f"Loading {path.name}...")
                    call_command("loaddata", str(path))
        except Exception as exc:
            raise CommandError(
                f"Failed to load one of the files: {exc}\n"
                "This usually means a file isn't a valid backup fixture, or the database's "
                "schema doesn't match what these files expect (wrong codebase version). "
                "Nothing from this run was committed — the database is unchanged."
            )

        self.stdout.write(self.style.SUCCESS(f"Restored {len(entries)} incremental backup(s) successfully."))

    def _collect_files(self):
        """
        Every .yaml in the incremental folder, parsed via the naming
        convention itself (no separate manifest file). Any file that
        doesn't match the expected pattern is a hard error — better to
        fail loudly than silently skip or misorder something.
        """
        paths = sorted(INCREMENTAL_DIR.glob("*.yaml"))
        if not paths:
            raise CommandError(
                f"No .yaml files found in {INCREMENTAL_DIR}. "
                "Unzip your downloaded incremental backups and place them there, then re-run this command."
            )

        entries = []
        for path in paths:
            match = INCREMENTAL_RE.match(path.name)
            if not match:
                raise CommandError(
                    f"'{path.name}' doesn't match the expected incremental backup filename pattern "
                    f"(backup-incremental-<from>-to-<to>.yaml). Remove or rename it, or double-check "
                    f"you placed the right file in the right folder, then re-run this command."
                )
            covers_from = _parse_stamp(match.group(1))
            covers_to = _parse_stamp(match.group(2))
            entries.append((path, covers_from, covers_to))

        entries.sort(key=lambda e: e[1])
        return entries

    def _get_full_backup_anchor(self):
        """
        If a full backup file is present alongside, its covers_to becomes
        the required starting point for the first incremental — verifying
        the chain all the way back to the full backup, not just among the
        incrementals themselves. If none is present, the first incremental
        is trusted as the starting point with a printed warning.
        """
        full_files = sorted(FULL_DIR.glob("*.yaml"))
        if not full_files:
            self.stdout.write(self.style.WARNING(
                f"No full backup .yaml found in {FULL_DIR} — cannot verify the incremental "
                "chain starts right after a full backup. Proceeding from the earliest incremental found."
            ))
            return None

        if len(full_files) > 1:
            names = "\n".join(f"  - {f.name}" for f in full_files)
            raise CommandError(
                f"Expected at most one .yaml file in {FULL_DIR}, found {len(full_files)}:\n{names}\n"
                "Remove the ones that aren't the anchor for this restore and re-run this command."
            )

        match = FULL_RE.match(full_files[0].name)
        if not match:
            raise CommandError(
                f"'{full_files[0].name}' in {FULL_DIR} doesn't match the expected full backup "
                "filename pattern (backup-full-<timestamp>.yaml). Rename it back to how it was "
                "downloaded, or remove it if it doesn't belong there."
            )
        return _parse_stamp(match.group(1))

    def _validate_chain(self, files, anchor):
        """
        Returns (valid_prefix, gap). gap is None if the whole chain is
        continuous; otherwise it's the point where the check first failed,
        and valid_prefix is everything confirmed continuous before it.
        """
        expected_start = anchor
        valid_prefix = []

        for path, covers_from, covers_to in files:
            if expected_start is not None and covers_from != expected_start:
                return valid_prefix, {
                    "expected": expected_start,
                    "found_file": path,
                    "found_from": covers_from,
                }
            valid_prefix.append((path, covers_from, covers_to))
            expected_start = covers_to

        return valid_prefix, None

    def _prompt_gap(self, gap):
        self.stdout.write(self.style.ERROR(
            f"\nGap detected in the incremental chain:\n"
            f"  Expected the next file to start at: {gap['expected'].strftime(STAMP_FORMAT)}\n"
            f"  But '{gap['found_file'].name}' starts at: {gap['found_from'].strftime(STAMP_FORMAT)}\n"
            f"  A file covering {gap['expected'].strftime(STAMP_FORMAT)} onward is missing.\n"
        ))
        while True:
            choice = input("[a]dd the missing file / [p]artial (stop before the gap) / [c]ancel: ").strip().lower()
            if choice in ("a", "p", "c"):
                return choice
            self.stdout.write("Please enter 'a', 'p', or 'c'.")
