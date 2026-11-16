"""Superusers can READ every user's chats (each other's too); nobody else can, and nobody can write."""
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from ai_agent import views
from ai_agent.models import Chat, ChatItem

from .helpers import make_admin, make_plain_user, make_superuser
from .test_api import call


class TeamChatsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.boss = make_superuser()
        self.boss2 = make_superuser("boss2@example.com")
        self.admin = make_admin()
        self.plain = make_plain_user()
        self.admin_chat = Chat.objects.create(user=self.admin, title="Admin sales")
        self.boss2_chat = Chat.objects.create(user=self.boss2, title="Boss2 profit")
        ChatItem.objects.create(chat=self.admin_chat, kind=ChatItem.Kind.USER, text="hello",
                                payload={"role": "user", "content": "hello"})
        ChatItem.objects.create(chat=self.admin_chat, kind=ChatItem.Kind.OTHER, text="",
                                payload={"type": "function_call", "name": "x"})
        ChatItem.objects.create(chat=self.admin_chat, kind=ChatItem.Kind.ASSISTANT, text="hi there",
                                payload={"role": "assistant", "content": "hi there"})

    def team_views(self):
        return [
            (views.TeamOwnersView, {}),
            (views.TeamUserChatsView, {"email": self.admin.email}),
            (views.TeamChatDetailView, {"chat_id": self.admin_chat.id}),
            (views.TeamChatMessagesView, {"chat_id": self.admin_chat.id}),
        ]

    def test_only_superusers_may_read(self):
        for view, kw in self.team_views():
            v = view.as_view()
            self.assertEqual(call(v, "get", "/t/", None, **kw).status_code, 401)
            self.assertEqual(call(v, "get", "/t/", self.plain, **kw).status_code, 403)
            self.assertEqual(call(v, "get", "/t/", self.admin, **kw).status_code, 403)     # staff, not superuser
            self.assertEqual(call(v, "get", "/t/", self.boss, **kw).status_code, 200)

    def test_nobody_can_write_through_the_team_endpoints(self):
        for view, kw in self.team_views():
            for method in ("post", "patch", "put", "delete"):
                self.assertEqual(call(view.as_view(), method, "/t/", self.boss, {}, **kw).status_code, 405, (view, method))
        self.admin_chat.refresh_from_db()
        self.assertEqual(self.admin_chat.title, "Admin sales")

    def test_user_list_has_every_owner_including_other_superusers(self):
        r = call(views.TeamOwnersView.as_view(), "get", "/t/", self.boss)
        rows = {row["email"]: row for row in r.data["results"]}
        self.assertEqual(set(rows), {self.admin.email, self.boss2.email})
        self.assertEqual(rows[self.admin.email]["chat_count"], 1)
        self.assertTrue(rows[self.boss2.email]["is_superuser"])
        self.assertTrue(rows[self.admin.email]["name"])

    def test_a_users_chats_and_their_messages_are_readable_text_only(self):
        r = call(views.TeamUserChatsView.as_view(), "get", "/t/", self.boss, email=self.admin.email)
        self.assertEqual([c["title"] for c in r.data["results"]], ["Admin sales"])
        self.assertEqual(r.data["results"][0]["owner_email"], self.admin.email)
        r = call(views.TeamChatMessagesView.as_view(), "get", "/t/", self.boss, chat_id=self.admin_chat.id)
        self.assertEqual([(m["role"], m["text"]) for m in r.data["results"]], [("assistant", "hi there"), ("user", "hello")])
        other = call(views.TeamUserChatsView.as_view(), "get", "/t/", self.boss, email=self.boss2.email)
        self.assertEqual([c["title"] for c in other.data["results"]], ["Boss2 profit"])

    def test_deleted_chats_stay_hidden(self):
        self.admin_chat.is_deleted = True
        self.admin_chat.save()
        self.assertEqual(call(views.TeamChatDetailView.as_view(), "get", "/t/", self.boss, chat_id=self.admin_chat.id).status_code, 404)
        self.assertEqual(call(views.TeamChatMessagesView.as_view(), "get", "/t/", self.boss, chat_id=self.admin_chat.id).status_code, 404)
        r = call(views.TeamOwnersView.as_view(), "get", "/t/", self.boss)
        self.assertEqual({row["email"] for row in r.data["results"]}, {self.boss2.email})

    def test_owners_own_endpoints_still_hide_other_peoples_chats(self):
        r = call(views.ChatDetailView.as_view(), "get", "/c/x/", self.boss, chat_id=self.admin_chat.id)
        self.assertEqual(r.status_code, 404)
        r = call(views.ChatMessagesView.as_view(), "post", "/c/x/", self.boss, {"content": "hi"}, chat_id=self.admin_chat.id)
        self.assertEqual(r.status_code, 404)

    def test_fixed_query_counts(self):
        with CaptureQueriesContext(connection) as q:
            call(views.TeamOwnersView.as_view(), "get", "/t/", self.boss)
        self.assertLessEqual(len(q), 4)         # auth user lookup is forced; count + page
        for _ in range(5):
            Chat.objects.create(user=self.admin, title="more")
        with CaptureQueriesContext(connection) as q:
            call(views.TeamUserChatsView.as_view(), "get", "/t/", self.boss, email=self.admin.email)
        self.assertLessEqual(len(q), 3)         # count + one joined page (no per-chat owner query)
