from django.urls import path

from .views import (
    BackupFlowStatsView,
    BackupHistoryListView,
    FullLocalBackupView,
    IncrementalLocalBackupView,
    FullRemoteBackupView,
    IncrementalRemoteBackupView,
)

urlpatterns = [
    path("full/local/",        FullLocalBackupView.as_view(),        name="backup-full-local"),
    path("incremental/local/", IncrementalLocalBackupView.as_view(), name="backup-incremental-local"),
    path("full/remote/",       FullRemoteBackupView.as_view(),       name="backup-full-remote"),
    path("incremental/remote/", IncrementalRemoteBackupView.as_view(), name="backup-incremental-remote"),
    path("stats/",              BackupFlowStatsView.as_view(),       name="backup-stats"),
    path("history/",            BackupHistoryListView.as_view(),     name="backup-history"),
]
