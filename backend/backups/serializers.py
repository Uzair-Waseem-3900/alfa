from rest_framework import serializers

from .models import BackupHistory


class BackupFlowStatsSerializer(serializers.Serializer):
    local_last_backup_at  = serializers.DateTimeField(allow_null=True)
    remote_last_backup_at = serializers.DateTimeField(allow_null=True)


class BackupHistorySerializer(serializers.ModelSerializer):
    triggered_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model  = BackupHistory
        fields = [
            "id", "backup_type", "destination", "status",
            "covers_from", "covers_to", "row_count", "schema_migrated",
            "error_message", "triggered_by", "created_at",
        ]
        read_only_fields = fields


class BackupManifestModelSerializer(serializers.Serializer):
    label = serializers.CharField()
    count = serializers.IntegerField()


class RemoteBackupResultSerializer(serializers.Serializer):
    backup_type      = serializers.CharField()
    covers_from      = serializers.DateTimeField(allow_null=True)
    covers_to        = serializers.DateTimeField()
    row_count        = serializers.IntegerField()
    models           = BackupManifestModelSerializer(many=True)
    schema_migrated  = serializers.BooleanField()
