from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsSuperuserOnly
from .selectors import get_activity_events, get_activity_stats
from .serializers import (
    ActivityEventReadSerializer, ActivityStatsSerializer, ToggleTrackingRequestSerializer,
)
from .services import set_tracking_enabled


class ActivityEventListView(generics.ListAPIView):
    """
    GET /activity-log/events/
    Filters: user_id, action, app_label, model_name, search, date_from,
    date_to, high_risk=true. Superuser only.
    """
    permission_classes = [IsSuperuserOnly]
    serializer_class = ActivityEventReadSerializer

    def get_queryset(self):
        p = self.request.query_params
        return get_activity_events(
            user_id    = p.get("user_id"),
            action     = p.get("action"),
            app_label  = p.get("app_label"),
            model_name = p.get("model_name"),
            search     = p.get("search"),
            date_from  = p.get("date_from"),
            date_to    = p.get("date_to"),
            high_risk  = p.get("high_risk") in ("true", "1", "True"),
        )


class ActivityStatsView(APIView):
    """GET /activity-log/stats/ — O(1) singleton read. Superuser only."""
    permission_classes = [IsSuperuserOnly]

    def get(self, request):
        stats = get_activity_stats()
        return Response(ActivityStatsSerializer(stats).data)


class ActivityTrackingToggleView(APIView):
    """
    PATCH /activity-log/toggle/ — flips the global on/off switch.
    Body: {"enabled": true|false}. Superuser only.

    The toggle itself is always recorded as its own event, whether turning
    tracking on OR off — see services.set_tracking_enabled.
    """
    permission_classes = [IsSuperuserOnly]

    def patch(self, request):
        serializer = ToggleTrackingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        stats = set_tracking_enabled(
            enabled=serializer.validated_data["enabled"], user=request.user,
        )
        return Response(ActivityStatsSerializer(stats).data, status=status.HTTP_200_OK)
