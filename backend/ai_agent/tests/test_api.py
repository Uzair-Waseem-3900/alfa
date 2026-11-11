from unittest import mock

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory, force_authenticate

from ai_agent import views
from ai_agent.models import Chat, ChatItem, ChatRun

from .helpers import make_admin, make_plain_user, make_superuser

FACTORY = APIRequestFactory()


def call(view, method, path, user, data=None, **kwargs):
    request = getattr(FACTORY, method)(path, data, format="json") if data is not None else getattr(FACTORY, method)(path)
    if user is not None:
        force_authenticate(request, user=user)
    return view(request, **kwargs)


class ChatApiTests(TestCase):
    def setUp(self):
        cache.clear()   # DRF throttles live in the cache
        self.admin = make_admin()
        self.other = make_admin("admin2@example.com")
        self.plain = make_plain_user()

    # --- permissions ------------------------------------------------------
    def test_anonymous_gets_401_and_plain_user_403(self):
        v = views.ChatListCreateView.as_view()
        self.assertEqual(call(v, "get", "/c/", None).status_code, 401)
        self.assertEqual(call(v, "get", "/c/", self.plain).status_code, 403)
        self.assertEqual(call(v, "post", "/c/", self.plain, {}).status_code, 403)

    def test_superuser_allowed(self):
        self.assertEqual(call(views.ChatListCreateView.as_view(), "get", "/c/", make_superuser()).status_code, 200)

    # --- CRUD + isolation ----------------------------------------------------
    def test_create_list_rename_delete(self):
        r = call(views.ChatListCreateView.as_view(), "post", "/c/", self.admin, {})
        self.assertEqual(r.status_code, 201)
        chat_id = r.data["id"]

        r = call(views.ChatListCreateView.as_view(), "get", "/c/", self.admin)
        self.assertEqual(r.data["count"], 1)

        r = call(views.ChatDetailView.as_view(), "patch", "/c/x/", self.admin, {"title": "  Sales Q3  "}, chat_id=chat_id)
        self.assertEqual((r.status_code, r.data["title"]), (200, "Sales Q3"))

        r = call(views.ChatDetailView.as_view(), "patch", "/c/x/", self.admin, {"title": "   "}, chat_id=chat_id)
        self.assertEqual(r.status_code, 400)

        r = call(views.ChatDetailView.as_view(), "delete", "/c/x/", self.admin, chat_id=chat_id)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(Chat.objects.count(), 0)            # hidden...
        self.assertEqual(Chat.all_objects.count(), 1)         # ...but soft-deleted, not removed
        r = call(views.ChatListCreateView.as_view(), "get", "/c/", self.admin)
        self.assertEqual(r.data["count"], 0)

    def test_users_cannot_see_each_others_chats(self):
        chat = Chat.objects.create(user=self.admin, title="secret")
        ChatItem.objects.create(chat=chat, payload={}, kind="user", text="hi")

        self.assertEqual(call(views.ChatListCreateView.as_view(), "get", "/c/", self.other).data["count"], 0)
        for method, view, extra in [
            ("get", views.ChatDetailView, {}),
            ("patch", views.ChatDetailView, {"title": "x"}),
            ("delete", views.ChatDetailView, None),
            ("get", views.ChatMessagesView, None),
            ("post", views.ChatMessagesView, {"content": "hello"}),
        ]:
            r = call(view.as_view(), method, "/c/x/", self.other, extra, chat_id=chat.id)
            self.assertEqual(r.status_code, 404, f"{method} {view.__name__} leaked a foreign chat")
        self.assertFalse(ChatRun.objects.exists())

    # --- sending a message -------------------------------------------------------
    @mock.patch("ai_agent.tasks.run_agent_task.delay")
    def test_send_message_queues_run_and_titles_chat(self, delay):
        chat = Chat.objects.create(user=self.admin)
        r = call(views.ChatMessagesView.as_view(), "post", "/m/", self.admin, {"content": "  how much cash do we have?  "}, chat_id=chat.id)
        self.assertEqual(r.status_code, 202)
        run = ChatRun.objects.get(pk=r.data["run_id"])
        self.assertEqual((run.status, run.user_message), ("queued", "how much cash do we have?"))
        delay.assert_called_once_with(str(run.id))
        chat.refresh_from_db()
        self.assertEqual(chat.title, "how much cash do we have?")

    @mock.patch("ai_agent.tasks.run_agent_task.delay")
    def test_second_send_while_active_is_clean_400(self, delay):
        chat = Chat.objects.create(user=self.admin)
        call(views.ChatMessagesView.as_view(), "post", "/m/", self.admin, {"content": "one"}, chat_id=chat.id)
        r = call(views.ChatMessagesView.as_view(), "post", "/m/", self.admin, {"content": "two"}, chat_id=chat.id)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ChatRun.objects.filter(chat=chat).count(), 1)
        self.assertEqual(delay.call_count, 1)

    @mock.patch("ai_agent.tasks.run_agent_task.delay")
    def test_finished_run_allows_next_message(self, delay):
        chat = Chat.objects.create(user=self.admin)
        r = call(views.ChatMessagesView.as_view(), "post", "/m/", self.admin, {"content": "one"}, chat_id=chat.id)
        ChatRun.objects.filter(pk=r.data["run_id"]).update(status="done")
        r = call(views.ChatMessagesView.as_view(), "post", "/m/", self.admin, {"content": "two"}, chat_id=chat.id)
        self.assertEqual(r.status_code, 202)

    @mock.patch("ai_agent.tasks.run_agent_task.delay")
    def test_stale_active_run_is_expired(self, delay):
        from datetime import timedelta
        from django.utils import timezone
        chat = Chat.objects.create(user=self.admin)
        stale = ChatRun.objects.create(chat=chat, user_message="old", status="running")
        ChatRun.objects.filter(pk=stale.pk).update(created_at=timezone.now() - timedelta(hours=2))
        r = call(views.ChatMessagesView.as_view(), "post", "/m/", self.admin, {"content": "new"}, chat_id=chat.id)
        self.assertEqual(r.status_code, 202)
        stale.refresh_from_db()
        self.assertEqual(stale.status, "error")

    @mock.patch("ai_agent.tasks.run_agent_task.delay", side_effect=ConnectionError("redis down"))
    def test_broker_down_gives_503_and_frees_chat(self, delay):
        chat = Chat.objects.create(user=self.admin)
        r = call(views.ChatMessagesView.as_view(), "post", "/m/", self.admin, {"content": "hi"}, chat_id=chat.id)
        self.assertEqual(r.status_code, 503)
        self.assertEqual(ChatRun.objects.get(chat=chat).status, "error")   # not stuck 'queued'

    def test_input_validation(self):
        chat = Chat.objects.create(user=self.admin)
        v = views.ChatMessagesView.as_view()
        for bad in ({}, {"content": ""}, {"content": "   "}, {"content": "x" * 2001}):
            self.assertEqual(call(v, "post", "/m/", self.admin, bad, chat_id=chat.id).status_code, 400, bad)

    # --- history ----------------------------------------------------------------
    def test_history_shows_only_visible_messages_newest_first(self):
        chat = Chat.objects.create(user=self.admin)
        ChatItem.objects.create(chat=chat, payload={}, kind="user", text="q1")
        ChatItem.objects.create(chat=chat, payload={}, kind="other", text="")
        ChatItem.objects.create(chat=chat, payload={}, kind="assistant", text="a1")
        r = call(views.ChatMessagesView.as_view(), "get", "/m/", self.admin, chat_id=chat.id)
        self.assertEqual([(m["role"], m["text"]) for m in r.data["results"]], [("assistant", "a1"), ("user", "q1")])

    # --- query counts (verification.md #6) ---------------------------------------
    def test_list_endpoints_have_small_fixed_query_counts(self):
        for i in range(25):
            c = Chat.objects.create(user=self.admin, title=f"c{i}")
            ChatItem.objects.create(chat=c, payload={}, kind="user", text="x")
        c = Chat.objects.filter(user=self.admin).first()
        for i in range(25):
            ChatItem.objects.create(chat=c, payload={}, kind="assistant", text="y")

        with CaptureQueriesContext(connection) as q:
            r = call(views.ChatListCreateView.as_view(), "get", "/c/", self.admin, None)
        self.assertEqual(len(r.data["results"]), 25)
        self.assertLessEqual(len(q), 3, [x["sql"] for x in q.captured_queries])

        with CaptureQueriesContext(connection) as q:
            r = call(views.ChatMessagesView.as_view(), "get", "/m/", self.admin, chat_id=c.id)
        self.assertLessEqual(len(q), 4, [x["sql"] for x in q.captured_queries])
