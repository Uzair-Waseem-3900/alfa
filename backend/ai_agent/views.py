import logging

from asgiref.sync import sync_to_async
from django.http import Http404, JsonResponse, StreamingHttpResponse
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken

from .models import ChatRun
from .permissions import IsAdminOrSuperuser
from .selectors import get_user_chat, get_user_chats, get_user_run, get_visible_messages
from .serializers import (
    ChatSerializer, ChatTitleSerializer, MessageSerializer, SendMessageSerializer,
)
from .services import chats as chat_service
from .services import runs as run_service
from .services.streaming import read_events


logger = logging.getLogger(__name__)


class ChatListCreateView(generics.ListCreateAPIView):
    """GET /api/agent/chats/  — my chats, newest first (paginated).
       POST                  — create an empty chat."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = ChatSerializer

    def get_queryset(self):
        return get_user_chats(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = chat_service.create_chat(user=self.request.user)


class ChatDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PATCH {title} / DELETE (soft) one of MY chats."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = ChatSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_object(self):
        return get_user_chat(self.request.user, self.kwargs["chat_id"])

    def partial_update(self, request, *args, **kwargs):
        chat = self.get_object()
        ser = ChatTitleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        chat = chat_service.rename_chat(chat=chat, title=ser.validated_data["title"])
        return Response(ChatSerializer(chat).data)

    def perform_destroy(self, instance):
        chat_service.soft_delete_chat(chat=instance)


class ChatMessagesView(generics.ListCreateAPIView):
    """GET  /api/agent/chats/<id>/messages/ — visible history, newest first (paginated).
       POST {content}                       — send a message -> 202 {run_id}."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = MessageSerializer
    throttle_classes = [AnonRateThrottle, UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "agent"

    def get_queryset(self):
        return get_visible_messages(get_user_chat(self.request.user, self.kwargs["chat_id"]))

    def create(self, request, *args, **kwargs):
        chat = get_user_chat(request.user, self.kwargs["chat_id"])
        ser = SendMessageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        run = run_service.start_run(chat=chat, content=ser.validated_data["content"])
        return Response({"run_id": str(run.id)}, status=status.HTTP_202_ACCEPTED)


# ---------------------------------------------------------------------------
# SSE — a plain async Django view (DRF has no async views). It authenticates
# with the same Bearer JWT as the rest of the API, so the frontend streams
# with fetch() (EventSource cannot send an Authorization header).
# ---------------------------------------------------------------------------

def _authenticate(request):
    """Sync: -> user or None. Same JWT rules as DRF's default auth class."""
    try:
        result = JWTAuthentication().authenticate(request)
    except (InvalidToken, AuthenticationFailed) as exc:
        logger.warning("agent stream auth rejected: %s", exc)
        return None
    if result is None:
        return None
    user = result[0]
    return user if (user.is_active and user.is_staff) else None


def _load_run(user, run_id):
    try:
        return get_user_run(user, run_id)
    except Http404:
        return None


async def run_stream(request, run_id):
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    user = await sync_to_async(_authenticate)(request)
    if user is None:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    run = await sync_to_async(_load_run)(user, run_id)
    if run is None:
        return JsonResponse({"detail": "Not found."}, status=404)

    async def is_active() -> bool:
        return await ChatRun.objects.filter(
            pk=run_id, status__in=ChatRun.ACTIVE_STATUSES,
        ).aexists()

    response = StreamingHttpResponse(
        read_events(run_id, request.headers.get("Last-Event-ID"), is_active),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"   # tell nginx-style proxies not to buffer
    return response
