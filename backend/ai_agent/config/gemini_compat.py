"""
Compatibility shims for Gemini's OpenAI-compatible endpoint, found in live
testing (openai-agents 0.24 + gemini-2.5-flash / flash-lite). Applied only to
the Gemini client.

1. Missing tool-call index (streaming).
   Gemini streams each tool call COMPLETE in its own chunk but leaves
   `tool_calls[].index` as None. The Agents SDK groups streamed tool-call
   fragments by `index`, so two tool calls in one turn were merged into one call
   with concatenated arguments (e.g. '{}{"limit":1}'), which Gemini then rejects
   with HTTP 400 INVALID_ARGUMENT on the next request.
   Fix: give every distinct tool-call id its own index as chunks pass through.

2. Empty completion after a tool result.
   With tools attached, Gemini sometimes returns NOTHING (no text, no tool call,
   completion_tokens=0, finish_reason "stop") right after a function result. The
   SDK then ends the run with an empty answer and the user sees a blank bubble.
   Fix: detect an empty completion and retry (EMPTY_RETRIES times). The retry
   request gets one extra nudge message appended; the nudge exists only on the
   wire, it is never stored in the chat session. For streams, the preamble
   chunks (role-only/empty deltas) are held back until real content arrives, so
   a retry is invisible to the SDK and the browser.

3. Stream cut off mid-answer.
   Occasionally Gemini's stream simply ends early WITHOUT its terminal chunk
   (no finish_reason), sometimes mid-sentence; the SDK treats that as a normal
   end and saves/shows a truncated answer. Content has already been forwarded by
   then, so it can't be retried invisibly. Instead, once a stream that carried
   content ends without a clean finish_reason ("stop"/"tool_calls"), raise
   IncompleteStreamError. services.runner catches it, rolls back what the
   attempt saved, tells the browser to clear the half-answer ("reset") and
   runs the question once more; if that is cut off too, the user gets a clear
   "cut off, try again" error rather than a silently truncated answer.
"""
import logging

logger = logging.getLogger(__name__)

EMPTY_RETRIES = 2
CLEAN_FINISH_REASONS = frozenset({"stop", "tool_calls", "function_call"})


class IncompleteStreamError(Exception):
    """A model stream ended without a clean finish_reason after sending content."""
NUDGE = {"role": "user", "content": "Please answer the question now, using the information above."}


# --- 1. tool-call index -----------------------------------------------------

class _IndexFixedStream:
    """Async-iterable proxy over an openai AsyncStream that repairs tool-call indexes."""

    def __init__(self, stream):
        self._stream = stream
        self._index_by_id: dict[str, int] = {}
        self._last_index = -1

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        async for chunk in self._stream:
            for choice in chunk.choices or []:
                for call in (choice.delta.tool_calls or []) if choice.delta else []:
                    if call.index is not None:
                        continue
                    if call.id:                       # a new call: allocate the next index
                        if call.id not in self._index_by_id:
                            self._last_index += 1
                            self._index_by_id[call.id] = self._last_index
                        call.index = self._index_by_id[call.id]
                    else:                             # a continuation fragment of the latest call
                        call.index = max(self._last_index, 0)
            yield chunk

    async def aclose(self):
        close = getattr(self._stream, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result

    def __getattr__(self, name):                       # response, etc.
        return getattr(self._stream, name)


# --- 2. empty completion ----------------------------------------------------

def _chunk_has_payload(chunk) -> bool:
    for choice in chunk.choices or []:
        delta = choice.delta
        if delta is not None and (delta.content or delta.tool_calls or getattr(delta, "refusal", None)):
            return True
    return False


def _completion_is_empty(response) -> bool:
    if not response.choices:
        return True
    message = response.choices[0].message
    return not (message.content or message.tool_calls)


def _retry_kwargs(kwargs: dict) -> dict:
    retry = dict(kwargs)
    retry["messages"] = [*kwargs["messages"], NUDGE]
    return retry


class _GuardedStream:
    """Fixes tool-call indexes and retries when the model produces nothing."""

    def __init__(self, original, args, kwargs, first_stream):
        self._original, self._args, self._kwargs, self._first = original, args, kwargs, first_stream
        self._current = first_stream

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        stream = self._first
        for attempt in range(EMPTY_RETRIES + 1):
            self._current = stream
            held, started, finish, chars = [], False, None, 0
            async for chunk in _IndexFixedStream(stream):
                for choice in chunk.choices or []:
                    if getattr(choice, "finish_reason", None):
                        finish = choice.finish_reason
                    if choice.delta is not None and choice.delta.content:
                        chars += len(choice.delta.content)
                if started:
                    yield chunk
                    continue
                held.append(chunk)
                if _chunk_has_payload(chunk):          # real content: release what we held back
                    started = True
                    for h in held:
                        yield h
                    held = []
            if started:
                if finish in CLEAN_FINISH_REASONS:
                    logger.info("Gemini turn finished: finish_reason=%s chars=%d", finish, chars)
                    return
                logger.warning("Gemini stream ended without a clean finish: finish_reason=%r chars=%d", finish, chars)
                raise IncompleteStreamError(f"stream ended with finish_reason={finish!r} after {chars} characters")
            if attempt == EMPTY_RETRIES:               # give up: let the SDK see the empty completion
                for h in held:
                    yield h
                return
            logger.warning("Gemini returned an empty streamed completion; retrying (%d/%d)", attempt + 1, EMPTY_RETRIES)
            stream = await self._original(*self._args, **_retry_kwargs(self._kwargs))

    async def aclose(self):
        close = getattr(self._current, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result

    def __getattr__(self, name):
        return getattr(self._current, name)


async def _retry_if_empty(original, args, kwargs, response):
    for attempt in range(EMPTY_RETRIES):
        if not _completion_is_empty(response):
            break
        logger.warning("Gemini returned an empty completion; retrying (%d/%d)", attempt + 1, EMPTY_RETRIES)
        response = await original(*args, **_retry_kwargs(kwargs))
    return response


def patch_gemini_client(client) -> None:
    """Wrap client.chat.completions.create with both shims above."""
    completions = client.chat.completions
    original = completions.create

    async def create(*args, **kwargs):
        result = await original(*args, **kwargs)
        if kwargs.get("stream"):
            return _GuardedStream(original, args, kwargs, result)
        return await _retry_if_empty(original, args, kwargs, result)

    completions.create = create
