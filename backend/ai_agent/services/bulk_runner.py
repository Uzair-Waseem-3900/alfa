"""
execute_bulk_item — the async body of the `agent_bulk` Celery task: one context-free agent run for ONE row, then a
code-decided final state and a live event. It never raises: whatever happens, the row ends in a state the user can act on.
"""
import asyncio
import logging

import openai
from agents import Runner
from agents.exceptions import AgentsException
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections

from ..config.configs import client_scope
from ..config.gemini_compat import IncompleteStreamError
from ..my_agents.bulk_agent import build_bulk_agent
from ..schemas.context import AgentContext
from ..selectors import bulk as sel
from . import bulk
from .runner import MAX_ATTEMPTS, _friendly_error
from .streaming import RunPublisher, batch_key

logger = logging.getLogger(__name__)


async def _drive(ctx: AgentContext, text: str) -> str:
    """One complete agent run (no session = no history). No tokens are published: only the outcome matters."""
    result = Runner.run_streamed(build_bulk_agent(), input=text, context=ctx, max_turns=settings.AGENT_MAX_TURNS)
    async for _event in result.stream_events():
        pass
    return str(result.final_output or "")


def _new_context(user, run_id, link_name_id) -> AgentContext:
    return AgentContext(user=user, run_id=str(run_id), chat_id=None, source="bulk", link_name_id=link_name_id)


async def _publish_state(publisher: RunPublisher, item_id: int, batch_id, *, idle_check: bool) -> None:
    item = await sync_to_async(lambda: bulk.BulkItem.objects.get(pk=item_id))()
    await publisher.publish("item", **bulk.item_event(item))
    if idle_check:
        status, active = await sync_to_async(bulk.refresh_batch_status)(batch_id)
        if not active:
            await publisher.publish("batch_idle", status=status)


async def execute_bulk_item(item_id) -> None:
    item = await sync_to_async(bulk.claim_item)(item_id)
    if item is None:   # duplicate delivery, cancelled batch, or gone
        return
    batch = item.batch
    publisher = RunPublisher(batch.id, key=batch_key(batch.id))
    run = None
    try:
        try:
            await _publish_state(publisher, item.pk, batch.id, idle_check=False)
        except Exception:  # noqa: BLE001 - live updates are optional: the page reads the database
            logger.exception("bulk row %s: could not publish 'processing'", item.pk)
        run = await sync_to_async(bulk.start_attempt)(item)
        user = batch.user
        outcome, final_text, error = None, "", ""
        ctx = _new_context(user, run.id, batch.link_name_id)
        try:
            if not (user.is_active and user.is_staff):
                raise PermissionError("user is no longer allowed to use the assistant")
            text = run.user_message
            async with client_scope(), asyncio.timeout(settings.AGENT_BULK_ITEM_TIMEOUT_SECONDS):
                for attempt in range(1, MAX_ATTEMPTS + 1):
                    try:
                        final_text = await _drive(ctx, text)
                        break
                    except IncompleteStreamError:
                        # never re-run a row that already wrote; otherwise start over once with a clean context
                        if attempt == MAX_ATTEMPTS or await sync_to_async(sel.created_action)(run_id=run.id):
                            raise
                        logger.warning("bulk row %s: model stream cut off (attempt %d); retrying", item.pk, attempt)
                        ctx = _new_context(user, run.id, batch.link_name_id)
        except Exception as exc:  # noqa: BLE001 - the row must always end in a usable state
            expected = (AgentsException, openai.OpenAIError, PermissionError, TimeoutError, IncompleteStreamError)
            if isinstance(exc, expected):
                logger.warning("bulk row %s failed: %r", item.pk, exc)
            else:
                logger.exception("bulk row %s crashed", item.pk)
            error = _friendly_error(exc)
        outcome = ctx.outcome
        await sync_to_async(bulk.finalize_item)(
            item_id=item.pk, run_id=run.id, outcome=outcome, final_text=final_text, error=error)
    except Exception:  # noqa: BLE001 - e.g. the database is down; nothing more can be recorded safely
        logger.exception("bulk row %s: could not record the result", item_id)
        try:
            await sync_to_async(bulk.finalize_item)(
                item_id=item_id, run_id=run.id if run else None, outcome=bulk.BulkOutcome(), error=bulk.MSG_STALE)
        except Exception:  # noqa: BLE001
            logger.exception("bulk row %s: could not even mark it failed", item_id)
    finally:
        try:
            await _publish_state(publisher, item_id, batch.id, idle_check=True)
        except Exception:  # noqa: BLE001 - Redis down: the page still has the database
            logger.exception("bulk row %s: could not publish its state", item_id)
        await publisher.close()
        await sync_to_async(close_old_connections)()
