"""
Shared machinery for every agent tool.

`@agent_tool` turns a plain sync function `f(ctx, ...)` into an SDK
function_tool and adds what every DB-touching tool needs:

  * runs AS the asking user (activity_log attribution for catch-up writes —
    the SDK runs sync tools in a worker thread, where no request exists);
  * closes stale DB connections afterwards (to_thread pool threads never see
    Django's request_finished signal);
  * turns expected failures into a short message for the model, unexpected
    ones into a generic one (never a stack trace into the LLM), and logs timing;
  * caps output size so a big table can't blow up the model's context.
"""
import functools
import json
import logging
import time
from decimal import Decimal

from agents import function_tool
from django.conf import settings
from django.db import connections

from activity_log.middleware import acting_as

logger = logging.getLogger(__name__)

MAX_TOOL_CHARS = 6000
SLOW_TOOL_SECONDS = 0.2   # the project's per-endpoint budget; slower is logged as a warning


class ToolInputError(Exception):
    """Bad/unsupported input — the message is shown to the model verbatim."""


def row_cap() -> int:
    return settings.AGENT_TOOL_ROW_CAP


def money(value) -> str:
    """Decimal -> '1234.50' (always a string: JSON floats lose precision)."""
    return f"{Decimal(value or 0):.2f}"


def clamp_limit(limit: int | None, default: int = 10) -> int:
    """Row limit the model asked for, bounded by AGENT_TOOL_ROW_CAP."""
    return max(1, min(limit or default, row_cap()))


def to_text(payload) -> str:
    """Compact JSON for the model (Decimal/date -> str), size-capped."""
    text = json.dumps(payload, default=str, separators=(",", ":"), ensure_ascii=False)
    if len(text) > MAX_TOOL_CHARS:
        text = text[:MAX_TOOL_CHARS] + '..."[truncated: narrow the search or period]"'
    return text


def agent_tool(func=None, **tool_kwargs):
    def decorate(f):
        @functools.wraps(f)
        def wrapper(ctx, *args, **kwargs):
            started = time.perf_counter()
            try:
                with acting_as(ctx.context.user):
                    return f(ctx, *args, **kwargs)
            except ToolInputError as exc:
                return f"Cannot do that: {exc}"
            except Exception:
                logger.exception("agent tool %s failed", f.__name__)
                return "The tool failed to read the data. Tell the user something went wrong and to try again."
            finally:
                connections.close_all()   # dedicated to_thread worker thread: don't leave its connection open
                elapsed = time.perf_counter() - started
                level = logging.WARNING if elapsed > SLOW_TOOL_SECONDS else logging.INFO
                logger.log(level, "agent tool %s took %.0f ms", f.__name__, elapsed * 1000)

        return function_tool(wrapper, **tool_kwargs)

    return decorate(func) if func is not None else decorate
