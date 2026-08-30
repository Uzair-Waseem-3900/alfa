from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.http import HttpResponse

from .models import BackupHistory
from .permissions import IsAdminOrSuperuser
from .selectors import get_all_backup_history, get_backup_flow_stats
from .serializers import BackupFlowStatsSerializer, BackupHistorySerializer, RemoteBackupResultSerializer
from .services import remote_backup_configured, run_local_backup, run_remote_backup


class BackupFlowStatsView(APIView):
    """
    GET /api/backups/stats/
    Just the two watermarks — when the last local/remote backup ran.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        serializer = BackupFlowStatsSerializer(get_backup_flow_stats())
        return Response(serializer.data)


class BackupHistoryListView(generics.ListAPIView):
    """
    GET /api/backups/history/
    Every backup run ever attempted, newest first — global default pagination.
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class   = BackupHistorySerializer

    def get_queryset(self):
        return get_all_backup_history()


class _LocalBackupView(APIView):
    """
    Shared body for both local backup endpoints — streams a zip containing
    a single Django fixture-format YAML file straight back as a download.
    Nothing is retained server-side. Restoring it later is: unzip, then
    `python manage.py loaddata <file>` against a fresh database — no custom
    import script needed.
    """
    permission_classes = [IsAdminOrSuperuser]
    backup_type = None  # set by subclass

    def post(self, request):
        try:
            zip_bytes, filename = run_local_backup(backup_type=self.backup_type, user=request.user)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        response = HttpResponse(zip_bytes, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class FullLocalBackupView(_LocalBackupView):
    """
    POST /api/backups/full/local/
    Every row in the system, from day one to now — streamed as a zipped
    fixture-format YAML download. Updates BackupFlow.local_last_backup_at.
    """
    backup_type = BackupHistory.BackupType.FULL


class IncrementalLocalBackupView(_LocalBackupView):
    """
    POST /api/backups/incremental/local/
    Only rows changed since the last successful LOCAL backup (full or
    incremental) — streamed as a zipped fixture-format YAML download.
    """
    backup_type = BackupHistory.BackupType.INCREMENTAL


class _RemoteBackupView(APIView):
    """
    Shared body for both remote backup endpoints — writes the collected
    data directly into the configured remote Postgres (Supabase/Neon).
    """
    permission_classes = [IsAdminOrSuperuser]
    backup_type = None  # set by subclass

    def post(self, request):
        if not remote_backup_configured():
            return Response(
                {"detail": "No remote backup database configured (BACKUP_DATABASE is not set)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = run_remote_backup(backup_type=self.backup_type, user=request.user)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        serializer = RemoteBackupResultSerializer(result)
        return Response(serializer.data)


class FullRemoteBackupView(_RemoteBackupView):
    """
    POST /api/backups/full/remote/
    Every row in the system, from day one to now — migrated + loaded
    directly into the configured remote database. Updates
    BackupFlow.remote_last_backup_at.
    """
    backup_type = BackupHistory.BackupType.FULL


class IncrementalRemoteBackupView(_RemoteBackupView):
    """
    POST /api/backups/incremental/remote/
    Only rows changed since the last successful REMOTE backup (full or
    incremental) — loaded directly into the configured remote database.
    """
    backup_type = BackupHistory.BackupType.INCREMENTAL
