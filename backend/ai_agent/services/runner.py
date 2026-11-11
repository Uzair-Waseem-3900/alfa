"""
execute_run — the async body of the Celery task: run the agent for one
ChatRun and translate SDK stream events into Redis stream events.
"""
import asyncio
import logging

import openai
from agents import Runner
from agents.exceptions import AgentsException, MaxTurnsExceeded
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections

from ..models import ChatRun
from ..my_agents.main_agent import build_agent
from ..my_tool import step_label
from ..schemas.context import AgentContext
from . import runs as run_service
from .session import DjangoSession
from .streaming import RunPublisher

logger = logging.getLogger(__name__)

MSG_BUSY = "The AI service is busy right now. Please try again in a minute."
MSG_TURNS = "I couldn't finish that within my step limit. Try asking a narrower question."
MSG_TIMEOUT = "That took too long, so I stopped. Try a narrower question."
MSG_FAILED = "Something went wrong while answering. Please try again."


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, MaxTurnsExceeded):
        return MSG_TURNS
    if isinstance(exc, TimeoutError):
        return MSG_TIMEOUT
    if isinstance(exc, openai.RateLimitError):
        return MSG_BUSY
    return MSG_FAILED


async def execute_run(run_id) -> None:
    try:
        run = await ChatRun.objects.select_related("chat", "chat__user").aget(pk=run_id)
    except ChatRun.DoesNotExist:   # chat deleted / stale message: nothing to do
        logger.warning("agent run %s no longer exists; skipping", run_id)
        return

    # Duplicate delivery / already handled -> do nothing.
    if not await sync_to_async(run_service.mark_running)(run_id):
        return

    publisher = RunPublisher(run_id)
    try:
        user = run.chat.user
        if not (user.is_active and user.is_staff):
            raise PermissionError("user is no longer allowed to use the assistant")

        result = Runner.run_streamed(
            build_agent(),
            input=run.user_message,
            session=DjangoSession(run.chat_id),
            context=AgentContext(user=user),
            max_turns=settings.AGENT_MAX_TURNS,
        )

        tool_names: dict[str, str] = {}   # call_id -> tool name
        # Hard ceiling so a stuck model/tool can never wedge a chat (the solo
        # pool does not enforce CELERY_TASK_TIME_LIMIT).
        async with asyncio.timeout(settings.AGENT_RUN_TIMEOUT_SECONDS):
            async for event in result.stream_events():
                if event.type == "raw_response_event":
                    if getattr(event.data, "type", "") == "response.output_text.delta":
                        await publisher.token(event.data.delta)
                elif event.type == "run_item_stream_event":
                    if event.name == "tool_called":
                        raw = event.item.raw_item
                        name, call_id = getattr(raw, "name", ""), getattr(raw, "call_id", "")
                        tool_names[call_id] = name
                        await publisher.publish("step", call_id=call_id, name=name, label=step_label(name))
                    elif event.name == "tool_output":
                        raw = event.item.raw_item
                        call_id = raw.get("call_id", "") if isinstance(raw, dict) else getattr(raw, "call_id", "")
                        await publisher.publish("step_done", call_id=call_id, name=tool_names.get(call_id, ""))

        await publisher.flush_tokens()
        await publisher.publish("done", text=str(result.final_output or ""))
        await sync_to_async(run_service.mark_done)(run_id)

    except Exception as exc:  # noqa: BLE001 - last line of defence: the run must always end
        body = getattr(exc, "body", None)   # openai.APIStatusError carries the provider's reason
        if not isinstance(exc, (AgentsException, openai.OpenAIError, PermissionError, TimeoutError)):
            logger.exception("agent run %s crashed", run_id)
        else:
            logger.warning("agent run %s failed: %r %s", run_id, exc, f"body={body}" if body else "")
        # Release the chat FIRST: if Redis is also down, publishing below can
        # raise, and the run must not stay 'running' until the stale cutoff.
        await sync_to_async(run_service.mark_error)(run_id, f"{type(exc).__name__}: {exc}")
        try:
            await publisher.flush_tokens()
            await publisher.publish("error", message=_friendly_error(exc))
        except Exception:  # noqa: BLE001
            logger.exception("could not publish the error event for run %s", run_id)
    finally:
        await publisher.close()
        # Async-ORM calls ran in Django's thread-sensitive executor thread;
        # release its connection from that same thread.
        await sync_to_async(close_old_connections)()
