from django.db.models import QuerySet

from .models import BackupFlow, BackupHistory


def get_all_backup_history() -> QuerySet:
    return BackupHistory.objects.all().select_related("triggered_by")


def get_backup_flow_stats() -> dict:
    flow = BackupFlow.get_instance()
    return {
        "local_last_backup_at": flow.local_last_backup_at,
        "remote_last_backup_at": flow.remote_last_backup_at,
    }
