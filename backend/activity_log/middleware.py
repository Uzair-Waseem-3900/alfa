import threading

_state = threading.local()


def get_current_user():
    """
    Returns the user attached to the currently-executing request, or None
    outside a request (management command, shell, etc.) —
    activity_log.tracking's signal receiver treats that as "system", never
    crashes on a missing user.

    Reads request.user FRESH on every call rather than snapshotting it once
    — this app authenticates via DRF's JWTAuthentication, which resolves
    request.user lazily *inside* the view (APIView.dispatch ->
    perform_authentication), not by the time Django's own middleware chain
    runs. CurrentUserMiddleware stores the request object itself (below);
    DRF's Request.user setter writes the resolved user back onto that same
    underlying HttpRequest object once authentication succeeds, so by the
    time a tracked model is actually saved (always after authentication,
    inside the view body), this lookup sees the real JWT-authenticated user
    — reading it any earlier would silently see AnonymousUser instead.
    """
    request = getattr(_state, "request", None)
    return getattr(request, "user", None) if request is not None else None


class CurrentUserMiddleware:
    """
    Stashes the request object in thread-local storage so the
    post_save/post_delete signal receivers in activity_log.tracking — which
    Django never gives direct access to the request — can attribute a
    tracked write to whoever made it. Always clears the slot in `finally`,
    so a thread reused for a later request (thread-pooled WSGI servers)
    never leaks the previous request's user into an unrelated write.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _state.request = request
        try:
            return self.get_response(request)
        finally:
            _state.request = None
