"""
The "Wake up" button.

A sleeping free-tier server (Render) only finishes waking if the request that knocked stays
OPEN while it boots, which takes anywhere from 30 to 90 seconds. A 5-second knock that is
abandoned on timeout never wakes it. But holding a web request open that long would freeze a
single-worker server for everyone (and gunicorn kills requests after 30s).

So the long wait happens on a background thread: the first press starts ONE knock per partner
that stays open for up to HOLD_SECONDS, while the browser's requests (every few seconds) come
straight back with the knock's current state. Nothing is stored in the database.

This is used only by the button. Every operation that changes something still uses the plain
5-second readiness gate (client.ensure_awake): partner asleep => nothing happens.
"""

import logging
import threading
import time

logger = logging.getLogger("b2b.wake")

HOLD_SECONDS = 85.0          # how long one knock stays open (the browser gives up at 90s)
FIRST_ANSWER_WAIT = 2.5      # a partner that is already awake answers within this, so the first press says so at once
REMEMBER_SECONDS = 10.0      # a finished "awake" / "refused" answer is reused for this long, then re-checked

_lock = threading.Lock()
_knocks = {}


class _Knock:
    __slots__ = ("done", "status", "finished_at")

    def __init__(self):
        self.done = threading.Event()
        self.status = None
        self.finished_at = 0.0


def _run(knock: _Knock, partner: str, check) -> None:
    try:
        knock.status = check(partner, HOLD_SECONDS)
    except Exception as exc:  # noqa: BLE001 — nothing may escape a background thread
        logger.warning("b2b wake knock for %r failed: %s", partner, type(exc).__name__)
        knock.status = "asleep"
    finally:
        knock.finished_at = time.monotonic()
        knock.done.set()


def wake_partner(partner: str, check) -> str:
    """
    'awake' | 'asleep' | 'not_configured' for the Wake up button.

    `check(partner, timeout_seconds)` makes ONE signed readiness call that waits up to the timeout
    and returns one of those three words. It is called on a background thread, never inside a request.
    """
    started_now = False
    with _lock:
        knock = _knocks.get(partner)
        if knock is not None and knock.done.is_set():
            fresh = time.monotonic() - knock.finished_at < REMEMBER_SECONDS
            if not (fresh and knock.status in ("awake", "not_configured")):
                knock = None                      # old or inconclusive: knock again
        if knock is None:
            knock = _Knock()
            _knocks[partner] = knock
            try:
                threading.Thread(target=_run, args=(knock, partner, check), daemon=True, name="b2b-wake").start()
            except Exception as exc:  # noqa: BLE001
                logger.warning("b2b wake knock for %r could not start: %s", partner, type(exc).__name__)
                knock.status = "asleep"
                knock.finished_at = time.monotonic()
                knock.done.set()
            started_now = True

    if started_now:
        knock.done.wait(FIRST_ANSWER_WAIT)         # only the press that started the knock waits, and only briefly
    return knock.status if knock.done.is_set() and knock.status else "asleep"


def reset() -> None:
    """Forget every knock (tests)."""
    with _lock:
        _knocks.clear()
