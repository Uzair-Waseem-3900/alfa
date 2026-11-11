import asyncio
from types import SimpleNamespace

from django.test import SimpleTestCase

from ai_agent.config.gemini_compat import _IndexFixedStream, patch_streaming_tool_indexes


def chunk(*calls):
    """A streamed chunk carrying the given tool-call deltas."""
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(tool_calls=list(calls)))])


def call(id=None, index=None, args=""):
    return SimpleNamespace(id=id, index=index, function=SimpleNamespace(name="t", arguments=args))


async def aiter(items):
    for i in items:
        yield i


async def collect(stream):
    return [c async for c in stream]


class IndexShimTests(SimpleTestCase):
    def test_parallel_calls_without_index_get_distinct_indexes(self):
        a, b = call("function-call-A", args="{}"), call("function-call-B", args='{"limit":1}')
        # exactly what Gemini sent: each call whole, in its own chunk, index None
        asyncio.run(collect(_IndexFixedStream(aiter([chunk(a), chunk(b)]))))
        self.assertEqual((a.index, b.index), (0, 1))

    def test_existing_indexes_untouched_and_continuations_follow_latest_call(self):
        given = call("x", index=7)
        first, cont = call("y"), call(None, args="more")
        asyncio.run(collect(_IndexFixedStream(aiter([chunk(given), chunk(first), chunk(cont)]))))
        self.assertEqual(given.index, 7)
        self.assertEqual(cont.index, first.index)

    def test_chunks_without_tool_calls_pass_through(self):
        plain = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(tool_calls=None))])
        empty = SimpleNamespace(choices=[])
        out = asyncio.run(collect(_IndexFixedStream(aiter([plain, empty]))))
        self.assertEqual(out, [plain, empty])

    def test_only_streaming_requests_are_wrapped(self):
        async def original(*a, **kw):
            return "raw-response" if not kw.get("stream") else aiter([])

        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=original)))
        patch_streaming_tool_indexes(client)
        self.assertEqual(asyncio.run(client.chat.completions.create(stream=False)), "raw-response")
        self.assertIsInstance(asyncio.run(client.chat.completions.create(stream=True)), _IndexFixedStream)
