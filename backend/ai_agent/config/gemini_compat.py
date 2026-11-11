"""
Compatibility shim for Gemini's OpenAI-compatible endpoint.

Problem (found in live testing, openai-agents 0.24 + gemini-2.5-flash):
Gemini streams each tool call COMPLETE in its own chunk but leaves
`tool_calls[].index` as None. The Agents SDK groups streamed tool-call
fragments by `index`, so two tool calls in one turn were merged into a single
call with concatenated arguments (e.g. '{}{"limit":1}'). That corrupt call is
sent back on the next request and Gemini rejects it with HTTP 400
INVALID_ARGUMENT.

Fix: give every distinct tool-call id its own index as chunks pass through.
Applied only to the Gemini client; non-streaming responses are untouched.
"""


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


def patch_streaming_tool_indexes(client) -> None:
    """Wrap client.chat.completions.create so streamed responses get fixed indexes."""
    completions = client.chat.completions
    original = completions.create

    async def create(*args, **kwargs):
        result = await original(*args, **kwargs)
        return _IndexFixedStream(result) if kwargs.get("stream") else result

    completions.create = create
