"""
Run pipeline: execute_run (SDK events -> Redis stream -> run status) and the
SSE reader/view. The model is faked (no Gemini call); Redis is the real,
configured server, using unique per-run keys that are deleted afterwards.
"""
import asyncio
import json
from types import SimpleNamespace
from unittest import mock

import openai
import redis
from django.conf import settings
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework_simplejwt.tokens import AccessToken

from ai_agent.config.gemini_compat import IncompleteStreamError
from ai_agent.models import Chat, ChatItem, ChatRun
from ai_agent.services import runner, streaming

from .helpers import make_admin, make_plain_user


def delta(text):
    return SimpleNamespace(type="raw_response_event", data=SimpleNamespace(type="response.output_text.delta", delta=text))


def tool_called(name, call_id):
    return SimpleNamespace(type="run_item_stream_event", name="tool_called",
                           item=SimpleNamespace(raw_item=SimpleNamespace(name=name, call_id=call_id)))


def tool_output(call_id):
    return SimpleNamespace(type="run_item_stream_event", name="tool_output",
                           item=SimpleNamespace(raw_item={"call_id": call_id, "output": "..."}))


class FakeResult:
    def __init__(self, events, final="", error=None):
        self._events, self.final_output, self._error = events, final, error

    async def stream_events(self):
        for e in self._events:
            yield e
        if self._error:
            raise self._error


class ScriptedResult(FakeResult):
    """FakeResult that also writes to the chat session first, like a real run does."""

    def __init__(self, events, final="", error=None, session=None, add=None):
        super().__init__(events, final, error)
        self._session, self._add = session, add

    async def stream_events(self):
        if self._session is not None and self._add:
            await self._session.add_items(self._add)
        async for e in super().stream_events():
            yield e


def user_item(text):
    return {"role": "user", "content": text}


def assistant_item(text):
    return {"id": "m", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}]}


class SlowResult:
    final_output = ""

    async def stream_events(self):
        await asyncio.sleep(5)
        yield  # pragma: no cover


class RateLimited(openai.RateLimitError):
    def __init__(self):          # bypass the real constructor (needs an httpx response)
        Exception.__init__(self, "429")


class RedisCase(TransactionTestCase):
    def setUp(self):
        self.r = redis.Redis.from_url(settings.AGENT_REDIS_URL, decode_responses=True)
        self.r.ping()    # fail loudly if the configured Redis is unreachable
        self.admin = make_admin()
        self.chat = Chat.objects.create(user=self.admin)
        self.keys = []

    def tearDown(self):
        for k in self.keys:
            self.r.delete(k)

    def new_run(self, status="queued"):
        run = ChatRun.objects.create(chat=self.chat, user_message="how much cash?", status=status)
        self.keys.append(streaming.stream_key(run.id))
        return run

    def events_of(self, run):
        out = []
        for _id, f in self.r.xrange(streaming.stream_key(run.id)):
            out.append((f["event"], json.loads(f["data"])))
        return out


class ExecuteRunTests(RedisCase):
    def _execute(self, run, fake_result=None, build_agent_side_effect=None):
        with mock.patch.object(runner, "build_agent", side_effect=build_agent_side_effect), \
             mock.patch.object(runner.Runner, "run_streamed", return_value=fake_result):
            asyncio.run(runner.execute_run(run.id))

    def test_happy_path_streams_steps_tokens_and_done(self):
        run = self.new_run()
        fake = FakeResult(
            [tool_called("business_snapshot", "c1"), tool_output("c1"), delta("You have "), delta("PKR 5"), delta("00.")],
            final="You have PKR 500.",
        )
        self._execute(run, fake)

        events = self.events_of(run)
        kinds = [k for k, _ in events]
        self.assertEqual(kinds[0:2], ["step", "step_done"])
        self.assertEqual(kinds[-1], "done")
        self.assertEqual("".join(d["text"] for k, d in events if k == "token"), "You have PKR 500.")
        self.assertEqual(events[0][1], {"call_id": "c1", "name": "business_snapshot", "label": "Checking the overall position…"})
        self.assertEqual(events[1][1], {"call_id": "c1", "name": "business_snapshot"})
        self.assertEqual(events[-1][1], {"text": "You have PKR 500."})
        run.refresh_from_db()
        self.assertEqual(run.status, "done")
        self.assertIsNotNone(run.finished_at)
        self.assertGreater(self.r.ttl(streaming.stream_key(run.id)), 0)     # stream expires

    def test_rate_limit_becomes_friendly_error(self):
        run = self.new_run()
        self._execute(run, FakeResult([delta("par")], error=RateLimited()))
        kinds = [k for k, _ in self.events_of(run)]
        self.assertEqual(kinds[-1], "error")
        self.assertEqual(self.events_of(run)[-1][1]["message"], runner.MSG_BUSY)
        run.refresh_from_db()
        self.assertEqual(run.status, "error")

    def test_unexpected_crash_never_leaks_internals(self):
        run = self.new_run()
        self._execute(run, FakeResult([], error=ValueError("db password is hunter2")))
        self.assertEqual(self.events_of(run)[-1], ("error", {"message": runner.MSG_FAILED}))
        run.refresh_from_db()
        self.assertEqual(run.status, "error")

    def test_agent_build_failure_still_ends_the_run(self):
        run = self.new_run()
        self._execute(run, None, build_agent_side_effect=RuntimeError("no api key"))
        run.refresh_from_db()
        self.assertEqual(run.status, "error")
        self.assertEqual(self.events_of(run)[-1][0], "error")

    def test_hard_timeout_ends_the_run_with_a_friendly_error(self):
        run = self.new_run()
        with self.settings(AGENT_RUN_TIMEOUT_SECONDS=0.2):
            self._execute(run, SlowResult())
        self.assertEqual(self.events_of(run)[-1], ("error", {"message": runner.MSG_TIMEOUT}))
        run.refresh_from_db()
        self.assertEqual(run.status, "error")

    def test_redis_failure_while_reporting_error_still_frees_the_chat(self):
        run = self.new_run()
        real_publish = streaming.RunPublisher.publish

        async def publish(self_, event_type, **data):
            if event_type == "error":
                raise ConnectionError("redis went away")
            return await real_publish(self_, event_type, **data)

        with mock.patch.object(streaming.RunPublisher, "publish", publish):
            self._execute(run, FakeResult([], error=ValueError("boom")))
        run.refresh_from_db()
        self.assertEqual(run.status, "error")          # not stuck in 'running'

    def test_missing_run_is_skipped_quietly(self):
        import uuid
        asyncio.run(runner.execute_run(uuid.uuid4()))   # must not raise

    def test_user_who_lost_access_is_refused(self):
        self.admin.is_staff = False
        self.admin.save()
        run = self.new_run()
        with mock.patch.object(runner.Runner, "run_streamed") as rs, mock.patch.object(runner, "build_agent"):
            asyncio.run(runner.execute_run(run.id))
            rs.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(run.status, "error")

    def test_duplicate_delivery_is_ignored(self):
        run = self.new_run(status="running")
        with mock.patch.object(runner.Runner, "run_streamed") as rs:
            asyncio.run(runner.execute_run(run.id))
            rs.assert_not_called()
        self.assertEqual(self.events_of(run), [])
        run.refresh_from_db()
        self.assertEqual(run.status, "running")

    def test_session_and_context_are_passed_to_runner(self):
        run = self.new_run()
        with mock.patch.object(runner, "build_agent", return_value="AGENT"), \
             mock.patch.object(runner.Runner, "run_streamed", return_value=FakeResult([], "ok")) as rs:
            asyncio.run(runner.execute_run(run.id))
        kw = rs.call_args.kwargs
        self.assertEqual(kw["input"], "how much cash?")
        self.assertEqual(kw["session"].session_id, str(self.chat.id))
        self.assertEqual(kw["context"].user.email, self.admin.email)
        self.assertEqual(kw["max_turns"], settings.AGENT_MAX_TURNS)


class CutOffRetryTests(RedisCase):
    """The model stream ended early (IncompleteStreamError): roll back, reset, retry once."""

    def _run(self, run, script):
        """`script(n, session)` returns the ScriptedResult for attempt n (0-based)."""
        attempts = []

        def run_streamed(agent, **kw):
            attempts.append(1)
            return script(len(attempts) - 1, kw["session"])

        with mock.patch.object(runner, "build_agent"),              mock.patch.object(runner.Runner, "run_streamed", side_effect=run_streamed):
            asyncio.run(runner.execute_run(run.id))
        return len(attempts)

    def test_cut_off_attempt_is_rolled_back_reset_and_retried(self):
        run = self.new_run()

        def script(n, session):
            if n == 0:
                return ScriptedResult([delta("I am NYRA ... Retrieve tax positions and asset")],
                                      error=IncompleteStreamError("cut"), session=session,
                                      add=[user_item("who are you and who is your developer")])
            return ScriptedResult([delta("Full answer incl. the developer.")], final="Full answer incl. the developer.",
                                  session=session,
                                  add=[user_item("who are you and who is your developer"), assistant_item("Full answer incl. the developer.")])

        self.assertEqual(self._run(run, script), 2)

        events = self.events_of(run)
        kinds = [k for k, _ in events]
        self.assertEqual(kinds.count("reset"), 1)
        self.assertEqual(kinds[-1], "done")
        after_reset = events[kinds.index("reset") + 1:]
        self.assertEqual("".join(d["text"] for k, d in after_reset if k == "token"), "Full answer incl. the developer.")
        self.assertNotIn("asset", "".join(d.get("text", "") for k, d in after_reset))      # nothing stale after the reset
        self.assertEqual(events[-1][1], {"text": "Full answer incl. the developer."})
        self.assertEqual(dict(events)["reset"], {"reason": "cut_off"})

        # history holds ONLY the successful attempt: one user message, one assistant message
        self.assertEqual(list(ChatItem.objects.filter(chat=self.chat).order_by("id").values_list("kind", flat=True)),
                         ["user", "assistant"])
        run.refresh_from_db()
        self.assertEqual(run.status, "done")

    def test_cut_off_twice_ends_with_a_clear_error_not_a_silent_partial_answer(self):
        run = self.new_run()
        n_attempts = self._run(run, lambda n, s: ScriptedResult(
            [delta("half an ans")], error=IncompleteStreamError("cut"), session=s, add=[user_item("q")]))

        self.assertEqual(n_attempts, runner.MAX_ATTEMPTS)
        events = self.events_of(run)
        self.assertEqual([k for k, _ in events].count("reset"), 1)             # one retry, then give up
        self.assertEqual(events[-1], ("error", {"message": runner.MSG_CUT_OFF}))
        run.refresh_from_db()
        self.assertEqual(run.status, "error")

    def test_other_errors_are_not_retried(self):
        run = self.new_run()
        n_attempts = self._run(run, lambda n, s: FakeResult([], error=ValueError("boom")))
        self.assertEqual(n_attempts, 1)
        self.assertNotIn("reset", [k for k, _ in self.events_of(run)])

    def test_a_clean_run_never_resets(self):
        run = self.new_run()
        n_attempts = self._run(run, lambda n, s: FakeResult([delta("ok")], final="ok"))
        self.assertEqual(n_attempts, 1)
        self.assertNotIn("reset", [k for k, _ in self.events_of(run)])


class StreamReaderTests(RedisCase):
    def _collect(self, run, last_id=None, is_active=None):
        async def go():
            return [f async for f in streaming.read_events(run.id, last_id, is_active)]
        return asyncio.run(go())

    def _publish(self, run, *events):
        async def go():
            p = streaming.RunPublisher(run.id)
            for typ, data in events:
                await p.publish(typ, **data)
            await p.close()
        asyncio.run(go())

    def test_reader_yields_sse_frames_until_terminal(self):
        run = self.new_run()
        self._publish(run, ("token", {"text": "hi"}), ("done", {"text": "hi"}))
        frames = self._collect(run)
        self.assertEqual(len(frames), 2)
        self.assertRegex(frames[0], r"^id: \d+-\d+\nevent: token\ndata: \{\"text\":\"hi\"\}\n\n$")
        self.assertIn("event: done", frames[1])

    def test_reconnect_with_last_event_id_replays_only_the_rest(self):
        run = self.new_run()
        self._publish(run, ("token", {"text": "a"}), ("token", {"text": "b"}), ("done", {"text": "ab"}))
        frames = self._collect(run)
        first_id = frames[0].split("\n")[0].removeprefix("id: ")
        rest = self._collect(run, last_id=first_id)
        self.assertEqual(len(rest), 2)
        self.assertIn('"text":"b"', rest[0])

    def test_dead_run_without_terminal_event_ends_with_error(self):
        run = self.new_run(status="error")

        async def inactive():
            return False

        with mock.patch.object(streaming, "BLOCK_MS", 50):
            frames = self._collect(run, is_active=inactive)
        self.assertEqual(len(frames), 1)
        self.assertIn("event: error", frames[0])

    def test_token_batching_reduces_writes(self):
        run = self.new_run()

        async def go():
            p = streaming.RunPublisher(run.id)
            for _ in range(200):
                await p.token("x")
            await p.flush_tokens()
            await p.close()
        asyncio.run(go())
        text = "".join(d["text"] for k, d in self.events_of(run) if k == "token")
        self.assertEqual(text, "x" * 200)
        self.assertLess(len(self.events_of(run)), 200)


class StreamViewTests(RedisCase):
    def _get(self, run_id, user=None):
        headers = {}
        if user is not None:
            headers["Authorization"] = f"Bearer {AccessToken.for_user(user)}"
        url = reverse("agent-run-stream", kwargs={"run_id": run_id})

        async def go():
            resp = await self.async_client.get(url, headers=headers)
            body = b""
            if resp.status_code == 200:
                async for chunk in resp.streaming_content:
                    body += chunk
            return resp, body.decode()
        return asyncio.run(go())

    def test_requires_valid_token(self):
        run = self.new_run()
        self.assertEqual(self._get(run.id)[0].status_code, 401)

    def test_plain_user_forbidden_as_401(self):
        run = self.new_run()
        self.assertEqual(self._get(run.id, make_plain_user())[0].status_code, 401)

    def test_other_users_run_is_404(self):
        run = self.new_run()
        self.assertEqual(self._get(run.id, make_admin("admin2@example.com"))[0].status_code, 404)

    def test_owner_gets_event_stream(self):
        run = self.new_run()
        asyncio.run(self._pub(run))
        resp, body = self._get(run.id, self.admin)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/event-stream")
        self.assertEqual(resp["Cache-Control"], "no-cache")
        self.assertIn("event: done", body)

    async def _pub(self, run):
        p = streaming.RunPublisher(run.id)
        await p.publish("done", text="ok")
        await p.close()
