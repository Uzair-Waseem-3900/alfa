from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

BACKUP_DIR = Path(settings.BASE_DIR) / "backups" / "backup_files" / "full_backup_file"


class Command(BaseCommand):
    help = (
        "Restores a full backup. Place exactly one .yaml fixture file in "
        "backend/backups/backup_files/full_backup_file/ first (unzip it "
        "yourself if it's still the downloaded .zip), then run this command. "
        "Migrates the currently-configured 'default' database, then loads "
        "the fixture into it."
    )

    def handle(self, *args, **options):
        yaml_files = sorted(BACKUP_DIR.glob("*.yaml"))

        if not yaml_files:
            raise CommandError(
                f"No .yaml file found in {BACKUP_DIR}. "
                "Unzip your downloaded backup and place the single .yaml file there, then re-run this command."
            )

        if len(yaml_files) > 1:
            names = "\n".join(f"  - {f.name}" for f in yaml_files)
            raise CommandError(
                f"Expected exactly one .yaml file in {BACKUP_DIR}, found {len(yaml_files)}:\n{names}\n"
                "Remove the ones you don't want to restore and re-run this command."
            )

        backup_file = yaml_files[0]
        self.stdout.write(f"Restoring from: {backup_file.name}")

        self.stdout.write("Applying migrations to the current database...")
        call_command("migrate", interactive=False, verbosity=1)

        self.stdout.write("Loading backup data...")
        try:
            call_command("loaddata", str(backup_file))
        except Exception as exc:
            raise CommandError(
                f"Failed to load {backup_file.name}: {exc}\n"
                "This usually means the file isn't a valid backup fixture, or the database's "
                "schema doesn't match what this file expects (wrong codebase version)."
            )

        self.stdout.write(self.style.SUCCESS(f"Full backup restored successfully from {backup_file.name}."))
