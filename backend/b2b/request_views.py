import uuid as uuidlib

from rest_framework import generics, status as http
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from . import client
from .authentication import SignedPartnerAuthentication
from .permissions import IsAdminOrSuperuser, IsSignedPartner
from .request_selectors import get_local_products_by_code, get_purchase_request, list_purchase_requests
from .request_serializers import (
    CreateRequestSerializer, PurchaseRequestDetailSerializer, PurchaseRequestListSerializer,
)
from .request_services import (
    cancel_purchase_request, create_purchase_request, process_doorbell, run_catch_up, same_text,
)
from .views import (
    DEFAULT_PAGE_SIZE, MAX_PAGE, MAX_PAGE_SIZE, MAX_SEARCH_LENGTH, NOT_CONFIGURED_MESSAGE,
    UNREACHABLE_MESSAGE, ConsumerOnlyMixin, _known_provider, _positive_int,
)


def _flatten(errors):
    """The partner's own validation message (any nesting) as a flat list of strings."""
    if isinstance(errors, dict):
        return [m for value in errors.values() for m in _flatten(value)]
    if isinstance(errors, (list, tuple)):
        return [m for value in errors for m in _flatten(value)]
    return [str(errors)] if errors else []


def _failure(exc: client.ProviderError) -> Response:
    """Maps a client failure to a UI-safe response (never echoes provider internals)."""
    if isinstance(exc, client.ProviderInvalid):
        messages = [m[:300] for m in _flatten(exc.errors)[:20]]      # bounded: never relay an unbounded body
        return Response({"items": messages or ["The partner rejected the request."]},
                        status=http.HTTP_400_BAD_REQUEST)
    if isinstance(exc, (client.ProviderNotConfigured, client.ProviderRejected)):
        return Response({"detail": NOT_CONFIGURED_MESSAGE}, status=http.HTTP_400_BAD_REQUEST)
    return Response({"detail": UNREACHABLE_MESSAGE}, status=http.HTTP_503_SERVICE_UNAVAILABLE)


class ProviderProductSearchView(ConsumerOnlyMixin, APIView):
    """
    GET /b2b/providers/<provider>/products/?search=&page=&page_size=
    The partner's requestable products (priced only; code + name; price only when
    the partner shares its rate list with us). Each row is marked with this
    software's own matching product — same code AND name — or null when there is
    none, so the form can disable it with "Not in your catalog".
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, provider):
        _known_provider(provider)
        params = request.query_params
        try:
            data = client.search_products(
                provider,
                search=(params.get("search") or "").strip()[:MAX_SEARCH_LENGTH],
                page=_positive_int(params.get("page"), 1, MAX_PAGE),
                page_size=_positive_int(params.get("page_size"), DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE),
            )
        except (client.ProviderNotConfigured, client.ProviderRejected):
            return Response({"status": "not_configured", "detail": NOT_CONFIGURED_MESSAGE})
        except client.ProviderError:
            return Response({"detail": UNREACHABLE_MESSAGE}, status=http.HTTP_503_SERVICE_UNAVAILABLE)

        local = get_local_products_by_code(row["code"] for row in data["results"])   # one query for the page
        for row in data["results"]:
            product = local.get(row["code"])
            matches = product is not None and same_text(product.name, row["name"])
            row["local_product_id"] = product.id if matches else None
            row["in_catalog"] = matches
        return Response(data)


class PurchaseRequestListCreateView(ConsumerOnlyMixin, generics.ListCreateAPIView):
    """
    GET  /b2b/purchase-requests/?status=   this software's own requests, newest first
    POST /b2b/purchase-requests/           make a request (provider in the body)
    """
    permission_classes = [IsAdminOrSuperuser]
    serializer_class = PurchaseRequestListSerializer

    def get_queryset(self):
        return list_purchase_requests(status=self.request.query_params.get("status"))

    def create(self, request, *args, **kwargs):
        provider = request.data.get("provider") if isinstance(request.data, dict) else None
        _known_provider(provider or "")
        serializer = CreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            purchase_request, delivered = create_purchase_request(
                provider=provider, items=data["items"], note=data["note"], user=request.user,
                request_uuid=data.get("request_uuid"),
            )
        except client.ProviderError as exc:
            return _failure(exc)
        body = PurchaseRequestDetailSerializer(get_purchase_request(purchase_request.pk)).data
        body = dict(body, notice=None if delivered else (
            "The partner could not be reached. Your request is saved and will be sent automatically."
        ))
        return Response(body, status=http.HTTP_201_CREATED)


class PurchaseRequestDetailView(ConsumerOnlyMixin, APIView):
    """GET /b2b/purchase-requests/<id>/"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, pk):
        purchase_request = get_purchase_request(pk)
        if purchase_request is None:
            raise NotFound("Request not found.")
        return Response(PurchaseRequestDetailSerializer(purchase_request).data)


class PurchaseRequestCancelView(ConsumerOnlyMixin, APIView):
    """POST /b2b/purchase-requests/<id>/cancel/ — decided by the partner: only a still-pending request cancels."""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, pk):
        try:
            cancel_purchase_request(request_id=pk)
        except client.ProviderError as exc:
            return _failure(exc)
        return Response(PurchaseRequestDetailSerializer(get_purchase_request(pk)).data)


class PurchaseRequestSyncView(ConsumerOnlyMixin, APIView):
    """POST /b2b/purchase-requests/sync/ — "check for updates now" (bypasses the one-minute gate)."""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request):
        return Response({"updated": run_catch_up(force=True)})


class PartnerDecidedView(APIView):
    """
    POST /b2b/partner/purchase-requests/decided/   — the "doorbell"
    Called (signed) by a partner software when it has decided one of OUR requests.
    The body only names the request; the real details are fetched with our own
    signed call, so there is a single code path whether we were rung or woke up.
    Always answers quickly with the same body; failures are retried by catch-up.
    """
    authentication_classes = [SignedPartnerAuthentication]
    permission_classes = [IsSignedPartner]

    def post(self, request):
        raw = request.data.get("request_uuid") if isinstance(request.data, dict) else None
        try:
            request_uuid = uuidlib.UUID(str(raw))
        except ValueError:
            return Response({"ok": False}, status=http.HTTP_400_BAD_REQUEST)
        process_doorbell(provider=request.user.partner_name, request_uuid=request_uuid)
        return Response({"ok": True})
