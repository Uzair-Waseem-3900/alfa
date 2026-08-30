from django.conf import settings
from django.db import models


class BackupFlow(models.Model):
    """
    Single live record remembering only the last backup point per
    destination — nothing else. Never created manually — managed exclusively
    via backups.services. The actual backup content is never stored here or
    anywhere server-side: local backups stream straight to the browser,
    remote backups write directly into the configured remote database.
    """
    local_last_backup_at  = models.DateTimeField(null=True, blank=True,
                                 help_text="Exact as_of timestamp the last successful LOCAL backup (full or incremental) covered up to.")
    remote_last_backup_at = models.DateTimeField(null=True, blank=True,
                                 help_text="Exact as_of timestamp the last successful REMOTE backup (full or incremental) covered up to.")

    class Meta:
        verbose_name        = "Backup Flow"
        verbose_name_plural = "Backup Flow"

    def __str__(self):
        return f"BackupFlow — local: {self.local_last_backup_at}, remote: {self.remote_last_backup_at}"

    @classmethod
    def get_instance(cls):
        """Always returns the single BackupFlow record, creating it if needed."""
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance


class BackupHistory(models.Model):
    """
    Audit trail — one row per backup run. Records exactly what range of data
    a backup covered (covers_from/covers_to), never the data itself.
    """
    class BackupType(models.TextChoices):
        FULL        = "full", "Full"
        INCREMENTAL = "incremental", "Incremental"

    class Destination(models.TextChoices):
        LOCAL  = "local", "Local"
        REMOTE = "remote", "Remote"

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED  = "failed", "Failed"

    backup_type  = models.CharField(max_length=15, choices=BackupType.choices)
    destination  = models.CharField(max_length=10, choices=Destination.choices)
    status       = models.CharField(max_length=10, choices=Status.choices)

    # The exact range of source data this run covered — null covers_from on
    # a full backup means "day one". Both are the fixed timestamps captured
    # once at the start of collection, never re-evaluated mid-run.
    covers_from  = models.DateTimeField(null=True, blank=True)
    covers_to    = models.DateTimeField()

    row_count      = models.PositiveIntegerField(default=0)
    error_message  = models.TextField(blank=True, default="")

    # Remote runs only: True when this run had to bring the remote database's
    # schema up to date before backing up — in which case backup_type is
    # forced to FULL regardless of what was requested, as a safety
    # re-baseline (see backups.services._ensure_remote_schema_synced).
    schema_migrated = models.BooleanField(default=False)

    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="backup_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name        = "Backup History"
        verbose_name_plural = "Backup History"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"{self.get_backup_type_display()} {self.get_destination_display()} backup — {self.status} ({self.created_at})"
