import io
import zipfile
from collections import defaultdict
from itertools import chain

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.exceptions import FieldDoesNotExist
from django.core.management import call_command
from django.db import connections, transaction
from django.db.migrations.recorder import MigrationRecorder

from .models import BackupFlow, BackupHistory


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

def _iter_backup_models():
    """
    Every model across the project's own apps (EXTERNAL_APPS) — never
    Django's own framework tables (auth groups/permissions, sessions,
    contenttypes, JWT blacklist), and never this app's own bookkeeping
    models (BackupFlow/BackupHistory — backing up backup metadata is
    pointless and would grow every run).
    """
    for app_label in settings.EXTERNAL_APPS:
        if app_label == "backups":
            continue
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            continue
        for model in app_config.get_models():
            yield model


def _get_timestamp_field(model) -> str | None:
    """
    Prefer 'updated_at' (AuditMixin's edit-tracking field) for incremental
    filtering; fall back to 'created_at' if that's all a model has; None
    means this model has no timestamp to filter by, so every backup —
    incremental or not — includes it in full (cheap, these are small
    lookup/config tables).
    """
    for field_name in ("updated_at", "created_at"):
        try:
            model._meta.get_field(field_name)
            return field_name
        except FieldDoesNotExist:
            continue
    return None


def _base_queryset(model):
    """
    Full backup content, not the soft-delete-filtered default — a backup
    that silently dropped soft-deleted rows wouldn't be a real backup.
    """
    manager = model.all_objects if hasattr(model, "all_objects") else model._default_manager
    return manager.all()


# ---------------------------------------------------------------------------
# Collection — the one function every backup endpoint (local/remote,
# full/incremental) funnels through
# ---------------------------------------------------------------------------

def collect_backup_data(*, since=None, as_of) -> dict:
    """
    Returns {
        "fixture_yaml": "<single Django-fixture-format YAML string>",
        "manifest_models": [{"label": ..., "count": ...}, ...],
        "row_count": <total>,
    }

    `fixture_yaml` is ONE combined serialization of every included row,
    across every model, in the exact format `manage.py dumpdata --format yaml`
    produces — which means restoring it is just `manage.py loaddata <file>`,
    no custom import script needed. Model order follows settings.EXTERNAL_APPS (already
    roughly FK-dependency-ordered: users, purchases, billing, ... last),
    same order `loaddata` would need to insert rows without FK violations.

    `as_of` is captured ONCE by the caller before this runs — every model is
    filtered by that same fixed timestamp, so the backup represents one
    precise, reproducible point in time regardless of how long collection
    itself takes or what writes land on the live tables while it runs.
    """
    manifest_models = []
    total_rows = 0
    querysets = []

    for model in _iter_backup_models():
        label = f"{model._meta.app_label}.{model._meta.model_name}"
        qs = _base_queryset(model)

        ts_field = _get_timestamp_field(model)
        if ts_field:
            qs = qs.filter(**{f"{ts_field}__lte": as_of})
            if since is not None:
                qs = qs.filter(**{f"{ts_field}__gt": since})

        count = qs.count()
        if count == 0:
            continue

        querysets.append(qs.order_by("pk"))
        manifest_models.append({"label": label, "count": count})
        total_rows += count

    fixture_yaml = serializers.serialize("yaml", chain(*querysets))
    return {"fixture_yaml": fixture_yaml, "manifest_models": manifest_models, "row_count": total_rows}


# ---------------------------------------------------------------------------
# Local delivery — one fixture file, zipped for compression, streamed
# straight back; nothing kept server-side. Restoring it is unzip, then
# `manage.py loaddata <file>`.
# ---------------------------------------------------------------------------

def _zip_single_file(*, inner_filename: str, content: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_filename, content)
    return buffer.getvalue()


def run_local_backup(*, backup_type: str, user) -> tuple[bytes, str]:
    """
    backup_type: BackupHistory.BackupType.FULL | INCREMENTAL
    Returns (zip_bytes, filename) — a zip containing exactly one YAML
    fixture file. Raises on failure (view logs the BackupHistory row
    either way, via try/except around this call).
    """
    from django.utils import timezone

    as_of = timezone.now()
    flow = BackupFlow.get_instance()
    since = flow.local_last_backup_at if backup_type == BackupHistory.BackupType.INCREMENTAL else None

    if backup_type == BackupHistory.BackupType.INCREMENTAL and since is None:
        # No prior local backup exists yet — "everything since the last
        # backup" is meaningless (there isn't one), so this degenerates
        # into a full backup. Same precedent as the remote schema-change
        # auto-upgrade: silently do the correct thing instead of crashing
        # or producing an empty/misleading result.
        backup_type = BackupHistory.BackupType.FULL

    try:
        collected = collect_backup_data(since=since, as_of=as_of)

        to_stamp = as_of.strftime('%Y%m%d-%H%M%S')
        if backup_type == BackupHistory.BackupType.INCREMENTAL:
            # Embeds the exact covered range in the filename itself — no
            # separate manifest file needed for a restore script to detect
            # gaps in a chain of incremental files.
            from_stamp = since.strftime('%Y%m%d-%H%M%S')
            base_name = f"backup-incremental-{from_stamp}-to-{to_stamp}"
        else:
            base_name = f"backup-full-{to_stamp}"

        # Built BEFORE any success is recorded or the watermark advances —
        # if this fails, the failure path below runs instead, and neither
        # BackupHistory nor BackupFlow claims a backup that was never
        # actually produced.
        zip_bytes = _zip_single_file(inner_filename=f"{base_name}.yaml", content=collected["fixture_yaml"])
    except Exception as exc:
        BackupHistory.objects.create(
            backup_type=backup_type, destination=BackupHistory.Destination.LOCAL,
            status=BackupHistory.Status.FAILED, covers_from=since, covers_to=as_of,
            error_message=str(exc), triggered_by=user,
        )
        raise

    BackupHistory.objects.create(
        backup_type=backup_type, destination=BackupHistory.Destination.LOCAL,
        status=BackupHistory.Status.SUCCESS, covers_from=since, covers_to=as_of,
        row_count=collected["row_count"], triggered_by=user,
    )
    flow.local_last_backup_at = as_of
    flow.save(update_fields=["local_last_backup_at"])

    return zip_bytes, f"{base_name}.zip"


# ---------------------------------------------------------------------------
# Remote delivery — real schema mirror on the configured Postgres target
# ---------------------------------------------------------------------------

def remote_backup_configured() -> bool:
    return "backup_remote" in settings.DATABASES


def _get_applied_migrations(database_alias: str) -> set:
    return set(MigrationRecorder(connections[database_alias]).migration_qs.values_list("app", "name"))


def _ensure_remote_schema_synced() -> bool:
    """
    Compares applied migrations between 'default' (this working codebase's
    schema) and 'backup_remote'. Applies whatever the remote is missing —
    idempotent, and safe for the AddField/CreateModel-only migrations this
    project has (Postgres doesn't rebuild-and-drop-unrelated-columns the way
    SQLite did in the incident earlier this session).

    Returns True if the remote's schema had to change. The caller uses this
    to force a FULL backup afterward regardless of what was requested — a
    safety re-baseline so nothing from before the schema change is assumed
    already covered by an incremental watermark.

    Raises if the remote has migrations local doesn't — an unexpected
    divergence; proceeding against an unknown schema would be unsafe.
    """
    local_applied = _get_applied_migrations("default")
    remote_applied = _get_applied_migrations("backup_remote")

    extra_on_remote = remote_applied - local_applied
    if extra_on_remote:
        raise RuntimeError(
            f"Remote backup database has migrations not present in this codebase: "
            f"{sorted(extra_on_remote)}. Refusing to back up against an unexpectedly "
            f"diverged schema — investigate before retrying."
        )

    missing_on_remote = local_applied - remote_applied
    if not missing_on_remote:
        return False

    call_command("migrate", database="backup_remote", interactive=False, verbosity=0)

    still_missing = local_applied - _get_applied_migrations("backup_remote")
    if still_missing:
        raise RuntimeError(f"Remote database still missing migrations after migrate: {sorted(still_missing)}")

    return True


_PRUNE_BATCH_SIZE = 1000


def _prune_remote_model(model, seen_pks: set) -> None:
    """
    Deletes every row of `model` on the remote whose pk is NOT in `seen_pks`
    — same end result as `exclude(pk__in=seen_pks).delete()`, but without
    ever building one query carrying the full seen_pks list, or one DELETE
    matched against every other remote row at once. For a table that has
    grown to tens of thousands of rows, a single unbounded NOT IN/EXCLUDE
    query gets slow and memory-heavy; this reads the remote's existing pks
    (chunked, via .iterator(), read-only) into a plain list first — so no
    write happens while that read cursor is still open — then deletes the
    unseen ones in bounded batches.
    """
    remote_pks = list(
        _base_queryset(model).using("backup_remote")
        .order_by("pk").values_list("pk", flat=True)
        .iterator(chunk_size=_PRUNE_BATCH_SIZE)
    )
    to_delete = [pk for pk in remote_pks if pk not in seen_pks]
    for i in range(0, len(to_delete), _PRUNE_BATCH_SIZE):
        batch = to_delete[i:i + _PRUNE_BATCH_SIZE]
        _base_queryset(model).using("backup_remote").filter(pk__in=batch).delete()


def run_remote_backup(*, backup_type: str, user) -> dict:
    """
    Validates (and if needed, brings up to date) the remote database's
    schema before ever touching data, then loads the collected dataset
    directly into it via Django's deserializer. Returns a small summary
    dict for the response.
    """
    from django.utils import timezone

    if not remote_backup_configured():
        raise RuntimeError("No remote backup database configured (BACKUP_DATABASE is not set).")

    schema_migrated = _ensure_remote_schema_synced()
    if schema_migrated:
        # Schema just changed on remote — force a full re-baseline instead
        # of trusting the old incremental watermark to still be meaningful.
        backup_type = BackupHistory.BackupType.FULL

    as_of = timezone.now()
    flow = BackupFlow.get_instance()
    since = flow.remote_last_backup_at if backup_type == BackupHistory.BackupType.INCREMENTAL else None

    if backup_type == BackupHistory.BackupType.INCREMENTAL and since is None:
        # Same as the local path — no prior remote backup exists, so
        # "since last backup" is meaningless; do a full one instead.
        backup_type = BackupHistory.BackupType.FULL

    try:
        collected = collect_backup_data(since=since, as_of=as_of)

        with transaction.atomic(using="backup_remote"):
            seen_pks = defaultdict(set)
            for deserialized_obj in serializers.deserialize("yaml", collected["fixture_yaml"]):
                obj = deserialized_obj.object
                obj.save(using="backup_remote")
                seen_pks[type(obj)].add(obj.pk)

            if backup_type == BackupHistory.BackupType.FULL:
                # A full backup should leave the remote as an exact mirror,
                # not just an append/update target — prune anything on the
                # remote that's no longer in the source, including models
                # that now have zero rows at all (never touched above).
                # Incremental backups deliberately don't do this: a row
                # deleted between two incrementals has no "changed" event
                # an incremental filter can see, so hard deletes only
                # propagate to the remote on the next full backup.
                for model in _iter_backup_models():
                    _prune_remote_model(model, seen_pks.get(model, set()))
    except Exception as exc:
        BackupHistory.objects.create(
            backup_type=backup_type, destination=BackupHistory.Destination.REMOTE,
            status=BackupHistory.Status.FAILED, covers_from=since, covers_to=as_of,
            error_message=str(exc), triggered_by=user, schema_migrated=schema_migrated,
        )
        raise

    BackupHistory.objects.create(
        backup_type=backup_type, destination=BackupHistory.Destination.REMOTE,
        status=BackupHistory.Status.SUCCESS, covers_from=since, covers_to=as_of,
        row_count=collected["row_count"], triggered_by=user, schema_migrated=schema_migrated,
    )
    flow.remote_last_backup_at = as_of
    flow.save(update_fields=["remote_last_backup_at"])

    return {
        "backup_type": backup_type,
        "covers_from": since,
        "covers_to": as_of,
        "row_count": collected["row_count"],
        "models": collected["manifest_models"],
        "schema_migrated": schema_migrated,
    }
