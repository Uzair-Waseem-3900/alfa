"""
Gemini through its OpenAI-compatible endpoint (same idea as the learning
project's config/configs.py, but values come from Django settings).

The client is built PER RUN, never at import time: each Celery task runs its
own asyncio loop (asyncio.run), and an httpx connection pool created in one
loop breaks when reused from a later one.
"""
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar

from agents import AsyncOpenAI, OpenAIChatCompletionsModel, set_tracing_disabled
from django.conf import settings

from .gemini_compat import patch_gemini_client

logger = logging.getLogger(__name__)

# Tracing would try to upload to OpenAI, which we don't use.
set_tracing_disabled(True)

# Clients created while a client_scope() is active are closed when it exits.
_scope_clients: ContextVar[list | None] = ContextVar("agent_model_clients", default=None)


@asynccontextmanager
async def client_scope():
    """Close every model client built inside this block, before the event loop ends.

    Each run builds its own client (an httpx pool is bound to the loop that
    created it). Left unclosed, it is garbage-collected AFTER asyncio.run()
    has closed the loop, which logs "Task exception was never retrieved:
    Event loop is closed" on every question and leaves sockets to the GC."""
    clients: list = []
    token = _scope_clients.set(clients)
    try:
        yield
    finally:
        _scope_clients.reset(token)
        for client in clients:
            try:
                await client.close()
            except Exception:  # noqa: BLE001 - cleanup must never mask the real outcome
                logger.debug("could not close a model client", exc_info=True)


def build_model(model_name: str | None = None) -> OpenAIChatCompletionsModel:
    client = AsyncOpenAI(
        api_key=settings.GEMINI_API_KEY,
        base_url=settings.GEMINI_BASE_URL,
        max_retries=2,
        timeout=60.0,
    )
    patch_gemini_client(client)   # see gemini_compat: missing tool-call index, empty completions
    scope = _scope_clients.get()
    if scope is not None:
        scope.append(client)
    return OpenAIChatCompletionsModel(
        openai_client=client,
        model=model_name or settings.AGENT_MODEL,
    )
