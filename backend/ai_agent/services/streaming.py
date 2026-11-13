"""
Run events over Redis Streams (not Pub/Sub): a browser that disconnects or
refreshes mid-answer reconnects with Last-Event-ID and replays what it
missed. One stream per run, key prefix "agent:run:", short TTL.

Publisher  — used by the Celery task (async, redis.asyncio).
Reader     — used by the async SSE view; yields ready-to-send SSE frames.
"""
import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable

import redis.asyncio as aioredis
from django.conf import settings

from ..schemas.events import TERMINAL_EVENTS, dump_event

STREAM_PREFIX = "agent:run:"
BLOCK_MS = 15_000          # heartbeat interval while idle
TOKEN_FLUSH_SECONDS = 0.05  # batch token deltas: ~20 writes/s max instead of one per token


def stream_key(run_id) -> str:
    return f"{STREAM_PREFIX}{run_id}"


def new_client() -> aioredis.Redis:
    # The socket read timeout MUST exceed BLOCK_MS: XREAD BLOCK legitimately
    # sits idle for up to BLOCK_MS (an LLM call is silent for seconds), and
    # redis-py's default socket timeout would kill the stream mid-answer.
    return aioredis.from_url(
        settings.AGENT_REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=BLOCK_MS / 1000 + 15,
    )


class RunPublisher:
    def __init__(self, run_id, client: aioredis.Redis | None = None):
        self.key = stream_key(run_id)
        self.client = client or new_client()
        self._buffer: list[str] = []
        self._last_flush = time.monotonic()

    async def publish(self, event_type: str, **data) -> None:
        if event_type != "token":
            await self.flush_tokens()
        await self._xadd(event_type, dump_event(event_type, **data))

    async def token(self, text: str) -> None:
        self._buffer.append(text)
        if time.monotonic() - self._last_flush >= TOKEN_FLUSH_SECONDS:
            await self.flush_tokens()

    def discard_tokens(self) -> None:
        """Drop buffered-but-unsent tokens (the attempt they belong to is being abandoned)."""
        self._buffer = []

    async def flush_tokens(self) -> None:
        if self._buffer:
            text, self._buffer = "".join(self._buffer), []
            await self._xadd("token", dump_event("token", text=text))
        self._last_flush = time.monotonic()

    async def _xadd(self, event_type: str, data: str) -> None:
        pipe = self.client.pipeline(transaction=False)
        pipe.xadd(self.key, {"event": event_type, "data": data})
        pipe.expire(self.key, settings.AGENT_STREAM_TTL_SECONDS)
        await pipe.execute()

    async def close(self) -> None:
        await self.client.aclose()


def sse_frame(event_id: str, event_type: str, data: str) -> str:
    return f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"


async def read_events(
    run_id,
    last_event_id: str | None = None,
    is_active: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[str]:
    """Yield SSE frames until a terminal event. Replays from `last_event_id`
    (a Redis entry id) when the client reconnects.

    `is_active` is checked whenever the stream goes idle: if the run is no
    longer queued/running in the DB but no terminal event arrived (worker
    died, stream expired), emit a synthetic `error` and stop instead of
    pinging forever."""
    client = new_client()
    key = stream_key(run_id)
    cursor = last_event_id or "0-0"
    try:
        while True:
            resp = await client.xread({key: cursor}, block=BLOCK_MS, count=100)
            if not resp:
                if is_active is not None and not await is_active():
                    # Final drain: the terminal event may have landed between
                    # our read and the status check.
                    leftover = await client.xread({key: cursor}, count=100)
                    if leftover:
                        continue
                    yield sse_frame(
                        "end", "error",
                        dump_event("error", message="The response is no longer available."),
                    )
                    return
                yield ": ping\n\n"   # keep proxies from closing an idle stream
                continue
            for _key, entries in resp:
                for entry_id, fields in entries:
                    cursor = entry_id
                    event_type = fields["event"]
                    yield sse_frame(entry_id, event_type, fields["data"])
                    if event_type in TERMINAL_EVENTS:
                        return
    except asyncio.CancelledError:  # client went away
        raise
    finally:
        await client.aclose()
