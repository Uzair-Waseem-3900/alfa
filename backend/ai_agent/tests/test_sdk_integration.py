"""
The REAL openai-agents SDK driven against a scripted fake Gemini client (no
network, no quota). This is the test that proves the three Gemini workarounds
in config/gemini_compat.py work *through the SDK*, not just in isolation:

  * tool calls streamed without `index` are not merged into one corrupt call
  * an empty completion is retried (with the nudge)
  * a stream cut off without a finish signal surfaces as IncompleteStreamError
"""
import asyncio

from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool, set_tracing_disabled
from django.test import SimpleTestCase
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import (
    Choice, ChoiceDelta, ChoiceDeltaToolCall, ChoiceDeltaToolCallFunction,
)

from ai_agent.config.gemini_compat import NUDGE, IncompleteStreamError, patch_gemini_client

set_tracing_disabled(True)


def mk_chunk(content=None, tool_calls=None, finish=None, role=None):
    delta = ChoiceDelta.model_construct(content=content, role=role, tool_calls=tool_calls, function_call=None, refusal=None)
    choice = Choice.model_construct(index=0, delta=delta, finish_reason=finish, logprobs=None)
    return ChatCompletionChunk.model_construct(
        id="chunk-1", object="chat.completion.chunk", created=1, model="m", choices=[choice], usage=None,
    )


def mk_call(call_id, name, arguments):
    """A tool call exactly as Gemini streams it: whole, and with index=None."""
    return ChoiceDeltaToolCall.model_construct(
        index=None, id=call_id, type="function",
        function=ChoiceDeltaToolCallFunction.model_construct(name=name, arguments=arguments),
    )


async def aiter(items):
    for i in items:
        yield i


def scripted_agent(streams, tools=()):
    """An Agent whose model replays `streams`, one per model request."""
    client = AsyncOpenAI(api_key="test", base_url="http://127.0.0.1:9/v1")
    queue, requests = list(streams), []

    async def create(*args, **kwargs):
        requests.append(kwargs)
        return aiter(queue.pop(0))

    client.chat.completions.create = create
    patch_gemini_client(client)
    agent = Agent(
        name="t", instructions="be brief", tools=list(tools),
        model=OpenAIChatCompletionsModel(openai_client=client, model="m"),
    )
    return agent, requests


def run_agent(agent, text="hi"):
    async def go():
        result = Runner.run_streamed(agent, text, max_turns=5)
        async for _ in result.stream_events():
            pass
        return result
    return asyncio.run(go())


class SdkThroughShimTests(SimpleTestCase):
    def test_normal_streamed_answer(self):
        agent, requests = scripted_agent([[mk_chunk(role="assistant", content=""), mk_chunk(content="Hello "),
                                           mk_chunk(content="world", finish="stop")]])
        self.assertEqual(run_agent(agent).final_output, "Hello world")
        self.assertEqual(len(requests), 1)

    def test_cut_off_stream_raises_incomplete_stream_error_through_the_sdk(self):
        # the field failure: text stops mid-sentence and the stream just ends
        agent, _ = scripted_agent([[mk_chunk(role="assistant", content=""), mk_chunk(content="I cannot create, edit")]])
        with self.assertLogs("ai_agent.config.gemini_compat", level="WARNING"):
            with self.assertRaises(IncompleteStreamError):
                run_agent(agent)

    def test_two_parallel_tool_calls_without_index_both_run_with_their_own_arguments(self):
        seen = []

        @function_tool
        def tool_a() -> str:
            """a"""
            seen.append(("a", None))
            return "A-done"

        @function_tool
        def tool_b(limit: int) -> str:
            """b"""
            seen.append(("b", limit))
            return "B-done"

        agent, requests = scripted_agent([
            # turn 1: two tool calls, each whole in its own chunk, both index=None
            [mk_chunk(role="assistant", content=""),
             mk_chunk(tool_calls=[mk_call("call_a", "tool_a", "{}")]),
             mk_chunk(tool_calls=[mk_call("call_b", "tool_b", '{"limit":3}')], finish="tool_calls")],
            # turn 2: the answer
            [mk_chunk(content="Both done.", finish="stop")],
        ], tools=[tool_a, tool_b])

        result = run_agent(agent)
        self.assertEqual(sorted(seen, key=lambda t: t[0]), [("a", None), ("b", 3)])   # NOT merged into '{}{"limit":3}'
        self.assertEqual(result.final_output, "Both done.")
        sent_calls = [m for m in requests[1]["messages"] if m.get("tool_calls")][0]["tool_calls"]
        self.assertEqual(sorted(c["function"]["arguments"] for c in sent_calls), sorted(["{}", '{"limit":3}']))

    def test_empty_completion_is_retried_with_the_nudge_and_the_answer_arrives(self):
        agent, requests = scripted_agent([
            [mk_chunk(role="assistant", content=""), mk_chunk(finish="stop")],          # model said nothing
            [mk_chunk(role="assistant", content=""), mk_chunk(content="Here you go.", finish="stop")],
        ])
        self.assertEqual(run_agent(agent).final_output, "Here you go.")
        self.assertEqual(len(requests), 2)
        self.assertNotIn(NUDGE, requests[0]["messages"])
        self.assertEqual(requests[1]["messages"][-1], NUDGE)
