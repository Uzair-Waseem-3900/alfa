from django.test import TestCase

from ai_agent.models import Chat, ChatItem
from ai_agent.services.session import DjangoSession, classify, trim_to_user_boundary

from .helpers import make_admin


def user_msg(text):
    return {"role": "user", "content": text}


def asst_msg(text):
    return {"id": "m", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}]}


def call(name, call_id):
    return {"type": "function_call", "name": name, "call_id": call_id, "arguments": "{}"}


def output(call_id, text="ok"):
    return {"type": "function_call_output", "call_id": call_id, "output": text}


class ClassifyTests(TestCase):
    def test_classify(self):
        self.assertEqual(classify(user_msg("hi")), ("user", "hi"))
        self.assertEqual(classify({"role": "user", "content": [{"type": "input_text", "text": "a"}, {"type": "input_text", "text": "b"}]}), ("user", "ab"))
        self.assertEqual(classify(asst_msg("yo")), ("assistant", "yo"))
        self.assertEqual(classify(call("x", "1"))[0], "other")
        self.assertEqual(classify(output("1"))[0], "other")

    def test_trim_cuts_at_user_boundary(self):
        items = [output("1"), asst_msg("a"), user_msg("q"), call("t", "2"), output("2"), asst_msg("b")]
        self.assertEqual(trim_to_user_boundary(items), items[2:])
        self.assertEqual(trim_to_user_boundary([output("1"), asst_msg("a")]), [])


class SessionTests(TestCase):
    def setUp(self):
        self.chat = Chat.objects.create(user=make_admin())
        self.session = DjangoSession(self.chat.id)

    async def test_roundtrip_and_kinds(self):
        await self.session.add_items([user_msg("hello"), call("sales_summary", "c1"), output("c1"), asst_msg("done")])
        items = await self.session.get_items()
        self.assertEqual(len(items), 4)
        kinds = [k async for k in ChatItem.objects.filter(chat=self.chat).order_by("id").values_list("kind", flat=True)]
        self.assertEqual(kinds, ["user", "other", "other", "assistant"])

    async def test_guide_call_and_output_never_stored(self):
        await self.session.add_items([user_msg("q"), call("get_guide", "g1")])
        await self.session.add_items([output("g1", "BIG GUIDE TEXT"), call("tax_position", "t1"), output("t1"), asst_msg("a")])
        stored = await self.session.get_items()
        self.assertEqual(len(stored), 4)   # user, tax call, tax output, assistant
        self.assertFalse(any("g1" == i.get("call_id") for i in stored))

    async def test_history_window_keeps_tool_pairs_intact(self):
        await self.session.add_items([user_msg("old q"), asst_msg("old a"), user_msg("q"), call("t", "c"), output("c"), asst_msg("a")])
        # raw window of 3 = [call, output, assistant]: no user message in it. It must NOT
        # return a window that starts mid tool-call (orphaned output), and must NOT
        # drop all memory either: it reaches back to that turn's own user message.
        items = await self.session.get_items(limit=3)
        self.assertEqual(items, [user_msg("q"), call("t", "c"), output("c"), asst_msg("a")])
        items = await self.session.get_items(limit=4)    # window already starts at the user message
        self.assertEqual(items[0], user_msg("q"))
        self.assertEqual(len(items), 4)

    async def test_extension_gives_up_on_absurdly_long_turns(self):
        from ai_agent.services.session import EXTEND_FACTOR
        long_turn = [user_msg("q")]
        for i in range(2 * EXTEND_FACTOR + 5):
            long_turn += [call("t", f"c{i}"), output(f"c{i}")]
        await self.session.add_items(long_turn)
        # window of 2 is all tool items; the turn is far longer than 2 x EXTEND_FACTOR -> give up cleanly
        self.assertEqual(await self.session.get_items(limit=2), [])

    async def test_add_items_bumps_chat_updated_at(self):
        before = (await Chat.objects.aget(pk=self.chat.pk)).updated_at
        await self.session.add_items([user_msg("hi")])
        after = (await Chat.objects.aget(pk=self.chat.pk)).updated_at
        self.assertGreater(after, before)

    async def test_pop_and_clear(self):
        await self.session.add_items([user_msg("a"), asst_msg("b")])
        self.assertEqual(classify(await self.session.pop_item())[1], "b")
        await self.session.clear_session()
        self.assertEqual(await self.session.get_items(), [])
        self.assertIsNone(await self.session.pop_item())

    async def test_sessions_are_isolated_per_chat(self):
        other = await Chat.objects.acreate(user=await self.chat.__class__.user.field.related_model.objects.aget(pk=self.chat.user_id), title="other")
        await DjangoSession(other.id).add_items([user_msg("other chat")])
        await self.session.add_items([user_msg("mine")])
        self.assertEqual(await self.session.get_items(), [user_msg("mine")])

    async def test_marker_and_rollback_remove_only_the_abandoned_attempt(self):
        self.assertEqual(await self.session.last_item_id(), 0)               # empty chat
        await self.session.add_items([user_msg("old q"), asst_msg("old a")])
        marker = await self.session.last_item_id()
        self.assertGreater(marker, 0)

        # an attempt that saved its input + tool traffic, then got cut off
        # (the get_guide call is never stored, so 3 rows were written)
        await self.session.add_items([user_msg("new q"), call("get_guide", "g1"), call("tax_position", "t1"), output("t1")])
        self.assertEqual(await self.session.rollback_to(marker), 3)
        self.assertEqual(await self.session.get_items(), [user_msg("old q"), asst_msg("old a")])

    async def test_rollback_also_forgets_which_call_ids_were_skipped(self):
        marker = await self.session.last_item_id()
        await self.session.add_items([user_msg("q"), call("get_guide", "g1")])   # g1 is now remembered as skipped
        await self.session.rollback_to(marker)
        # a fresh attempt may legitimately reuse that id for a normal tool: it must be stored
        await self.session.add_items([user_msg("q"), call("tax_position", "g1"), output("g1")])
        self.assertEqual(len(await self.session.get_items()), 3)
