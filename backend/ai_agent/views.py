import logging

from asgiref.sync import sync_to_async
from django.http import Http404, JsonResponse, StreamingHttpResponse
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken

from .models import BulkItem, ChatRun
from .permissions import IsAdminOrSuperuser, IsSuperuser
from .selectors import bulk as bulk_sel
from .selectors import (
    get_any_chat, get_chat_owners, get_chats_of_owner, get_user_chat, get_user_chats, get_user_run,
    get_visible_messages,
)
from .serializers import (
    BulkAnswerSerializer, BulkBatchDetailSerializer, BulkBatchSerializer, BulkItemSerializer,
    CreateBulkBatchSerializer, LinkNameOptionSerializer, ChatOwnerSerializer, ChatSerializer, ChatTitleSerializer, MessageSerializer, SendMessageSerializer,
    TeamChatSerializer,
)
from .services import bulk as bulk_service
from .services import chats as chat_service
from .services import runs as run_service
from .schemas.events import BATCH_TERMINAL_EVENTS
from .services.streaming import batch_key, read_events


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
# Team chats — superusers may READ any user's chats (themselves included).
# GET only: no sending, renaming or deleting someone else's chat.
# ---------------------------------------------------------------------------

class TeamOwnersView(generics.ListAPIView):
    """GET /api/agent/team/users/ — users who have chats (paginated, most recently active first)."""
    permission_classes = [IsSuperuser]
    serializer_class = ChatOwnerSerializer

    def get_queryset(self):
        return get_chat_owners()


class TeamUserChatsView(generics.ListAPIView):
    """GET /api/agent/team/users/<email>/chats/ — that user's chats, newest first (paginated)."""
    permission_classes = [IsSuperuser]
    serializer_class = TeamChatSerializer

    def get_queryset(self):
        return get_chats_of_owner(self.kwargs["email"])


class TeamChatDetailView(generics.RetrieveAPIView):
    """GET /api/agent/team/chats/<id>/ — one chat with its owner."""
    permission_classes = [IsSuperuser]
    serializer_class = TeamChatSerializer

    def get_object(self):
        return get_any_chat(self.kwargs["chat_id"])


class TeamChatMessagesView(generics.ListAPIView):
    """GET /api/agent/team/chats/<id>/messages/ — history, newest first (paginated). Text only."""
    permission_classes = [IsSuperuser]
    serializer_class = MessageSerializer

    def get_queryset(self):
        return get_visible_messages(get_any_chat(self.kwargs["chat_id"]))


# ---------------------------------------------------------------------------
# Bulk invoices — one batch = many prompts, one context-free agent run each
# ---------------------------------------------------------------------------

class _BulkThrottled:
    throttle_classes = [AnonRateThrottle, UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "agent_bulk"


class BulkLinkNamesView(generics.ListAPIView):
    """GET /api/agent/bulk/link-names/ — the dropdown (customers are searched only under the chosen one)."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = LinkNameOptionSerializer

    def get_queryset(self):
        return bulk_sel.link_names()


class BulkBatchListCreateView(_BulkThrottled, generics.ListCreateAPIView):
    """GET  /api/agent/bulk/batches/ — my batches with row counts (paginated).
       POST {prompts, link_name_id?}  — create the batch and start it -> 201 (detail)."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = BulkBatchSerializer

    def get_queryset(self):
        return bulk_sel.get_user_batches(self.request.user)

    def create(self, request, *args, **kwargs):
        ser = CreateBulkBatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        batch = bulk_service.create_batch(
            user=request.user, prompts=ser.validated_data["prompts"], link_name_id=ser.validated_data.get("link_name_id"),
        )
        batch = bulk_sel.get_user_batch_with_items(request.user, batch.id)
        return Response(BulkBatchDetailSerializer(batch).data, status=status.HTTP_201_CREATED)


class BulkBatchDetailView(generics.RetrieveDestroyAPIView):
    """GET /api/agent/bulk/batches/<id>/ — the batch and every row (the page's source of truth).
       DELETE — soft delete (not while rows are still working)."""
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = BulkBatchDetailSerializer

    def get_object(self):
        batch = bulk_sel.get_user_batch(self.request.user, self.kwargs["batch_id"])
        bulk_service.resolve_stale_rows(batch.id)       # a row whose worker died must not look 'processing' forever
        return bulk_sel.get_user_batch_with_items(self.request.user, batch.id)

    def perform_destroy(self, instance):
        bulk_service.delete_batch(batch=instance)


class BulkCancelView(_BulkThrottled, APIView):
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, batch_id):
        batch = bulk_service.cancel_batch(batch=bulk_sel.get_user_batch(request.user, batch_id))
        return Response(BulkBatchDetailSerializer(bulk_sel.get_user_batch_with_items(request.user, batch.id)).data)


class _BulkItemAction(_BulkThrottled, APIView):
    permission_classes = [IsAdminOrSuperuser]

    def act(self, item, request):
        raise NotImplementedError

    def post(self, request, item_id):
        item = bulk_sel.get_user_item(request.user, item_id)
        return Response(BulkItemSerializer(self.act(item, request)).data)


class BulkAnswerView(_BulkItemAction):
    """POST {answer} — answer the agent's question; only that row runs again."""
    def act(self, item, request):
        ser = BulkAnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return bulk_service.answer_item(item=item, answer=ser.validated_data["answer"])


class BulkSkipView(_BulkItemAction):
    """POST — "I will do it myself": leave this row alone."""
    def act(self, item, request):
        return bulk_service.skip_item(item=item)


class BulkRetryView(_BulkItemAction):
    """POST — run a failed row again."""
    def act(self, item, request):
        return bulk_service.retry_item(item=item)


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


async def bulk_stream(request, batch_id):
    """GET /api/agent/bulk/batches/<id>/stream/ — live row updates (`item`, `batch_idle`) for MY batch.
    The page loads the batch from the database first; this only carries changes after that."""
    if request.method != "GET":
        return JsonResponse({"detail": "Method not allowed."}, status=405)

    user = await sync_to_async(_authenticate)(request)
    if user is None:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    def _owns() -> bool:
        try:
            bulk_sel.get_user_batch(user, batch_id)
            return True
        except Http404:
            return False

    if not await sync_to_async(_owns)():
        return JsonResponse({"detail": "Not found."}, status=404)

    async def is_active() -> bool:
        return await BulkItem.objects.filter(batch_id=batch_id, status__in=BulkItem.ACTIVE_STATUSES).aexists()

    response = StreamingHttpResponse(
        read_events(
            batch_id, request.headers.get("Last-Event-ID"), is_active,
            key=batch_key(batch_id), terminal=BATCH_TERMINAL_EVENTS, terminal_needs_idle=True,
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
