"""
Gemini through its OpenAI-compatible endpoint (same idea as the learning
project's config/configs.py, but values come from Django settings).

The client is built PER RUN, never at import time: each Celery task runs its
own asyncio loop (asyncio.run), and an httpx connection pool created in one
loop breaks when reused from a later one.
"""
from agents import AsyncOpenAI, OpenAIChatCompletionsModel, set_tracing_disabled
from django.conf import settings

from .gemini_compat import patch_streaming_tool_indexes

# Tracing would try to upload to OpenAI, which we don't use.
set_tracing_disabled(True)


def build_model(model_name: str | None = None) -> OpenAIChatCompletionsModel:
    client = AsyncOpenAI(
        api_key=settings.GEMINI_API_KEY,
        base_url=settings.GEMINI_BASE_URL,
        max_retries=2,
        timeout=60.0,
    )
    patch_streaming_tool_indexes(client)   # Gemini omits tool_call.index when streaming
    return OpenAIChatCompletionsModel(
        openai_client=client,
        model=model_name or settings.AGENT_MODEL,
    )
