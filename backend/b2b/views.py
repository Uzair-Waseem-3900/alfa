from rest_framework import generics, status as http
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from . import client, config
from .permissions import IsAdminOrSuperuser

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
MAX_PAGE = 1_000_000
MAX_SEARCH_LENGTH = 100

NOT_CONFIGURED_MESSAGE = (
    "The partner did not accept this connection. Check that the shared secret, "
    "this software's company name and the partner's address match on both sides."
)
UNREACHABLE_MESSAGE = (
    "The partner software could not be reached right now. Use the Wake up button, wait until it answers, and try again."
)
NOT_AWAKE_MESSAGE = (
    "The partner software is not awake right now, so nothing was changed. "
    "Press \"Wake up\", wait until it answers, and try again."
)


class ConsumerOnlyMixin:
    """The whole consumer half is switched off (404) unless B2B_CONSUMER_ENABLED."""

    def initial(self, request, *args, **kwargs):
        if not config.consumer_enabled():
            raise NotFound()
        super().initial(request, *args, **kwargs)


def _known_provider(provider: str) -> str:
    if provider not in config.provider_names():
        raise NotFound()
    return provider


def _positive_int(raw, default, maximum=None):
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value < 1:
        return default
    return min(value, maximum) if maximum else value


def _partner_failure(exc: client.ProviderError) -> Response:
    """Maps a client failure to a UI-safe response (never echoes provider details)."""
    if isinstance(exc, client.PartnerNotAwake):
        return Response({"code": "partner_not_awake", "detail": NOT_AWAKE_MESSAGE}, status=http.HTTP_409_CONFLICT)
    if isinstance(exc, (client.ProviderNotConfigured, client.ProviderRejected)):
        return Response({"status": "not_configured", "detail": NOT_CONFIGURED_MESSAGE})
    return Response({"detail": UNREACHABLE_MESSAGE}, status=http.HTTP_503_SERVICE_UNAVAILABLE)


class ProviderListView(ConsumerOnlyMixin, generics.ListAPIView):
    """GET /b2b/providers/ — the partner softwares this one is configured to read from."""
    permission_classes = [IsAdminOrSuperuser]

    def get_queryset(self):
        return [{"key": name} for name in config.provider_names()]

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(page)


class ProviderRateListView(ConsumerOnlyMixin, APIView):
    """
    GET /b2b/providers/<provider>/rate-list/?search=&page=&page_size=
    Live proxy: one signed call to the provider, no cache, no stored copy.
    Returns {status, count, total_pages, current_page, page_size, results[]};
    results are empty unless the provider reports status 'approved'.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, provider):
        _known_provider(provider)
        params = request.query_params
        try:
            data = client.fetch_rate_list(
                provider,
                search=(params.get("search") or "").strip()[:MAX_SEARCH_LENGTH],
                page=_positive_int(params.get("page"), 1, MAX_PAGE),
                page_size=_positive_int(params.get("page_size"), DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE),
            )
        except client.ProviderError as exc:
            return _partner_failure(exc)
        return Response(data)


class ProviderRequestView(ConsumerOnlyMixin, APIView):
    """POST /b2b/providers/<provider>/request/ — ask (or ask again) for access."""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, provider):
        _known_provider(provider)
        try:
            client.ensure_awake(provider)        # nothing is sent unless the partner answers
            return Response(client.request_access(provider))
        except client.ProviderError as exc:
            return _partner_failure(exc)


class ProviderWakeView(ConsumerOnlyMixin, APIView):
    """
    POST /b2b/providers/<provider>/wake/ — the admin pressed "Wake up". One readiness check
    (5s limit) of that partner's backend. The browser repeats it every few seconds, for at
    most 90 seconds, until it answers; nothing here changes any data.
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, provider):
        _known_provider(provider)
        status = client.wake_status(provider)
        if status == "awake":
            return Response({"awake": True})
        return Response({
            "awake": False, "reason": status,
            "detail": NOT_CONFIGURED_MESSAGE if status == "not_configured" else None,
        })
