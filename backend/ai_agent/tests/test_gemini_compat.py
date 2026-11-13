import asyncio
from types import SimpleNamespace

from django.test import SimpleTestCase

from ai_agent.config.gemini_compat import (
    EMPTY_RETRIES, NUDGE, IncompleteStreamError, _GuardedStream, _IndexFixedStream, patch_gemini_client,
)


def chunk(*calls, content=None, finish=None):
    """A streamed chunk carrying the given tool-call deltas and/or text."""
    delta = SimpleNamespace(tool_calls=list(calls) or None, content=content, refusal=None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish)])


def call(id=None, index=None, args=""):
    return SimpleNamespace(id=id, index=index, function=SimpleNamespace(name="t", arguments=args))


def response(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))])


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
        plain = SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(tool_calls=None, content="hi"))])
        empty = SimpleNamespace(choices=[])
        out = asyncio.run(collect(_IndexFixedStream(aiter([plain, empty]))))
        self.assertEqual(out, [plain, empty])


class FakeCompletions:
    """Stands in for client.chat.completions; hands out scripted results and records requests."""

    def __init__(self, results):
        self.results, self.requests = list(results), []

    async def create(self, *args, **kwargs):
        self.requests.append(kwargs)
        return self.results[min(len(self.requests), len(self.results)) - 1]


def make_client(results):
    completions = FakeCompletions(results)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    patch_gemini_client(client)
    return client, completions


MESSAGES = [{"role": "user", "content": "Who built you?"}, {"role": "tool", "content": "guide text"}]


class EmptyCompletionRetryTests(SimpleTestCase):
    # --- non-streaming ---------------------------------------------------
    def test_non_stream_retries_once_with_a_nudge_then_returns_the_answer(self):
        good = response(content="Uzair Waseem built me.")
        client, fake = make_client([response(), good])
        result = asyncio.run(client.chat.completions.create(messages=list(MESSAGES)))
        self.assertIs(result, good)
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(fake.requests[0]["messages"], MESSAGES)                 # first request untouched
        self.assertEqual(fake.requests[1]["messages"], [*MESSAGES, NUDGE])      # retry carries the nudge

    def test_non_stream_good_answer_is_not_retried(self):
        client, fake = make_client([response(content="hello")])
        asyncio.run(client.chat.completions.create(messages=list(MESSAGES)))
        self.assertEqual(len(fake.requests), 1)

    def test_non_stream_tool_call_counts_as_a_valid_completion(self):
        client, fake = make_client([response(tool_calls=[object()])])
        asyncio.run(client.chat.completions.create(messages=list(MESSAGES)))
        self.assertEqual(len(fake.requests), 1)

    def test_non_stream_gives_up_after_the_retry_budget(self):
        empty = response()
        client, fake = make_client([empty])
        result = asyncio.run(client.chat.completions.create(messages=list(MESSAGES)))
        self.assertIs(result, empty)
        self.assertEqual(len(fake.requests), 1 + EMPTY_RETRIES)

    # --- streaming ---------------------------------------------------------
    def test_stream_empty_attempt_is_invisible_and_retried(self):
        empty_stream = aiter([chunk(), chunk(finish="stop")])                      # preamble + finish, no content
        good = [chunk(), chunk(content="Uzair"), chunk(content=" built me", finish="stop")]
        client, fake = make_client([empty_stream, aiter(good)])

        stream = asyncio.run(client.chat.completions.create(messages=list(MESSAGES), stream=True))
        self.assertIsInstance(stream, _GuardedStream)
        got = asyncio.run(collect(stream))

        self.assertEqual(got, good)                                                # only the retry's chunks reach the SDK
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(fake.requests[1]["messages"], [*MESSAGES, NUDGE])
        self.assertTrue(fake.requests[1]["stream"])

    def test_stream_with_content_is_not_retried_and_keeps_order(self):
        chunks = [chunk(), chunk(content="a"), chunk(content="b"), chunk(finish="stop")]
        client, fake = make_client([aiter(chunks)])
        got = asyncio.run(collect(asyncio.run(client.chat.completions.create(messages=list(MESSAGES), stream=True))))
        self.assertEqual(got, chunks)
        self.assertEqual(len(fake.requests), 1)

    def test_stream_tool_call_counts_as_content_and_gets_an_index(self):
        tc = call("function-call-A", args="{}")
        client, fake = make_client([aiter([chunk(), chunk(tc), chunk(finish="tool_calls")])])
        got = asyncio.run(collect(asyncio.run(client.chat.completions.create(messages=list(MESSAGES), stream=True))))
        self.assertEqual(len(got), 3)
        self.assertEqual(len(fake.requests), 1)
        self.assertEqual(tc.index, 0)

    def test_stream_gives_up_after_the_retry_budget_and_passes_the_empty_stream_through(self):
        def empty():
            return aiter([chunk(), chunk(finish="stop")])
        client, fake = make_client([empty(), empty(), empty()])
        got = asyncio.run(collect(asyncio.run(client.chat.completions.create(messages=list(MESSAGES), stream=True))))
        self.assertEqual(len(fake.requests), 1 + EMPTY_RETRIES)
        self.assertEqual(len(got), 2)                                              # the SDK still sees a normal (empty) finish

    def test_only_streaming_requests_get_the_stream_wrapper(self):
        client, _ = make_client([response(content="x"), aiter([chunk(content="x")])])
        self.assertNotIsInstance(asyncio.run(client.chat.completions.create(messages=[])), _GuardedStream)
        self.assertIsInstance(asyncio.run(client.chat.completions.create(messages=[], stream=True)), _GuardedStream)


class CutOffStreamTests(SimpleTestCase):
    """A stream that carried content but ended without a clean finish_reason was cut off."""

    def _consume(self, chunks):
        client, _ = make_client([aiter(chunks)])
        stream = asyncio.run(client.chat.completions.create(messages=list(MESSAGES), stream=True))
        received = []

        async def go():
            async for c in stream:
                received.append(c)

        return received, go

    def test_content_without_finish_reason_raises_after_forwarding_the_partial_text(self):
        # exactly the field failure: "...I cannot create, edit" and then nothing
        received, go = self._consume([chunk(), chunk(content="I cannot create, edit")])
        with self.assertLogs("ai_agent.config.gemini_compat", level="WARNING"):
            with self.assertRaises(IncompleteStreamError):
                asyncio.run(go())
        self.assertEqual(len(received), 2)              # the partial text WAS forwarded (live streaming)

    def test_truncating_finish_reasons_also_raise(self):
        for reason in ("length", "content_filter"):
            received, go = self._consume([chunk(content="half an ans", finish=reason)])
            with self.assertLogs("ai_agent.config.gemini_compat", level="WARNING"):
                with self.assertRaises(IncompleteStreamError, msg=reason):
                    asyncio.run(go())

    def test_clean_finish_reasons_pass(self):
        for reason in ("stop", "tool_calls"):
            received, go = self._consume([chunk(content="whole answer", finish=reason)])
            asyncio.run(go())
            self.assertEqual(len(received), 1, reason)

    def test_tool_call_turn_cut_off_without_finish_also_raises(self):
        received, go = self._consume([chunk(call("function-call-A", args="{}"))])
        with self.assertLogs("ai_agent.config.gemini_compat", level="WARNING"):
            with self.assertRaises(IncompleteStreamError):
                asyncio.run(go())


class ClientScopeTests(SimpleTestCase):
    """Model clients must be closed before the run's event loop ends (no 'Event loop is closed' noise)."""

    def test_clients_built_inside_the_scope_are_closed_on_exit_even_after_an_error(self):
        from unittest import mock
        from ai_agent.config.configs import build_model, client_scope

        closed = []

        async def go():
            with self.settings(GEMINI_API_KEY="test-key"):
                try:
                    async with client_scope():
                        model = build_model()
                        original_close = model._client.close

                        async def spy_close():
                            closed.append(model._client)
                            await original_close()

                        model._client.close = spy_close
                        raise RuntimeError("the run failed")
                except RuntimeError:
                    pass

        asyncio.run(go())
        self.assertEqual(len(closed), 1)

    def test_building_a_model_outside_a_scope_registers_nothing(self):
        from ai_agent.config import configs
        with self.settings(GEMINI_API_KEY="test-key"):
            configs.build_model()
        self.assertIsNone(configs._scope_clients.get())

