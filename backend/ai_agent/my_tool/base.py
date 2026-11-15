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
from agents.function_schema import function_schema
from pydantic import ValidationError
from django.conf import settings
from django.db import connections

from activity_log.middleware import acting_as

logger = logging.getLogger(__name__)

MAX_TOOL_CHARS = 6000
SLOW_TOOL_SECONDS = 0.2   # the project's per-endpoint budget; slower is logged as a warning


# Re-exported so existing `from .base import ToolInputError` imports keep working.
from ..exceptions import ToolInputError  # noqa: E402,F401


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


def _tool_error(ctx, error) -> str:
    """Fallback when the SDK itself rejects the call (e.g. the arguments were not even valid JSON).
    Field-level problems are caught earlier, with names, by `_guard_arguments` below."""
    return f"Cannot do that: the arguments were not valid ({str(error)[:200]}). Nothing was changed. Fix the arguments and try again."


def _field_problems(error: ValidationError) -> str:
    """'lines.0.quantity: Input should be greater than or equal to 1; customer_id: Field required' —
    names and rules only, never the values the model sent."""
    return "; ".join(f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in error.errors()[:5])


def _guard_arguments(tool, wrapper, *, write: bool) -> None:
    """Pre-validate the call with the SAME pydantic model the SDK would use, so the model is told WHICH
    field is wrong. (By default the SDK redacts validation details for privacy, leaving only
    "Invalid JSON input for tool X": the model can't fix its call, retries blindly, and — seen live —
    may then claim success.) For tools that change data it also refuses undeclared arguments instead of
    letting the SDK silently drop them (the model could believe it set an advance/price/status)."""
    schema = function_schema(wrapper, strict_json_schema=tool.strict_json_schema)
    allowed = set(tool.params_json_schema.get("properties", {}))
    original = tool.on_invoke_tool

    async def guarded(ctx, input_json):
        try:
            data = json.loads(input_json or "{}")
        except ValueError:
            data = None
        if isinstance(data, dict):
            unknown = sorted(set(data) - allowed)
            if write and unknown:
                return (
                    f"Cannot do that: unknown argument(s) {', '.join(unknown)}. Nothing was changed. "
                    "Payments, advances, prices, shelves and status cannot be set by this tool."
                )
            try:
                schema.params_pydantic_model(**data)
            except ValidationError as exc:
                return (f"Cannot do that: the arguments were not valid ({_field_problems(exc)}). "
                        "Nothing was changed. Fix the arguments and try again.")
        return await original(ctx, input_json)

    tool.on_invoke_tool = guarded


def agent_tool(func=None, *, write=False, **tool_kwargs):
    """`write=True` marks a tool that CHANGES data: undeclared arguments are refused (not silently
    dropped) and an internal failure says plainly that the change was NOT made."""
    tool_kwargs.setdefault("failure_error_function", _tool_error)

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
                if write:
                    return ("The change was NOT made because of an internal error. Tell the user it failed and to try "
                            "again later. Never say it was created, changed or discarded.")
                return "The tool failed to read the data. Tell the user something went wrong and to try again."
            finally:
                connections.close_all()   # dedicated to_thread worker thread: don't leave its connection open
                elapsed = time.perf_counter() - started
                level = logging.WARNING if elapsed > SLOW_TOOL_SECONDS else logging.INFO
                logger.log(level, "agent tool %s took %.0f ms", f.__name__, elapsed * 1000)

        tool = function_tool(wrapper, **tool_kwargs)
        _guard_arguments(tool, wrapper, write=write)
        return tool

    return decorate(func) if func is not None else decorate
