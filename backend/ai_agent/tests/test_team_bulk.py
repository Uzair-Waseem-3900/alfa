"""Superusers can READ every user's bulk batches (each other's too); nobody else can, and nobody can write."""
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from ai_agent import views
from ai_agent.models import BulkBatch, BulkItem

from .helpers import make_admin, make_plain_user, make_superuser
from .test_api import call
from .test_bulk import BulkWorld


class TeamBulkTests(BulkWorld, TestCase):
    def setUp(self):
        cache.clear()
        self.build_world()                              # self.admin owns the first batch
        self.boss = make_superuser()
        self.boss2 = make_superuser("boss2@example.com")
        self.staff = make_admin("staff2@example.com")
        self.plain = make_plain_user()
        self.admin_batch = self.make_batch(["a", "b"])
        BulkItem.objects.filter(batch=self.admin_batch, position=1).update(
            status="done", bill_number="BILL-2026-0001", summary={"lines": [{"product": "Pen", "quantity": 1}], "grand_total": "100.00"})
        self.boss2_batch = self.make_batch(["z"], user=self.boss2)

    def team_views(self):
        return [
            (views.TeamBulkOwnersView, {}),
            (views.TeamBulkUserBatchesView, {"email": self.admin.email}),
            (views.TeamBulkBatchDetailView, {"batch_id": self.admin_batch.id}),
        ]

    def test_only_superusers_may_read(self):
        for view, kw in self.team_views():
            v = view.as_view()
            self.assertEqual(call(v, "get", "/t/", None, **kw).status_code, 401)
            self.assertEqual(call(v, "get", "/t/", self.plain, **kw).status_code, 403)
            self.assertEqual(call(v, "get", "/t/", self.staff, **kw).status_code, 403)      # staff, not superuser
            self.assertEqual(call(v, "get", "/t/", self.boss, **kw).status_code, 200)

    def test_nobody_can_write_through_the_team_endpoints(self):
        for view, kw in self.team_views():
            for method in ("post", "patch", "put", "delete"):
                self.assertEqual(call(view.as_view(), method, "/t/", self.boss, {}, **kw).status_code, 405, (view, method))
        self.admin_batch.refresh_from_db()
        self.assertEqual((self.admin_batch.title, self.admin_batch.is_deleted), ("", False))

    def test_the_owner_list_includes_other_superusers(self):
        r = call(views.TeamBulkOwnersView.as_view(), "get", "/t/", self.boss)
        rows = {row["email"]: row for row in r.data["results"]}
        self.assertEqual(set(rows), {self.admin.email, self.boss2.email})
        self.assertEqual(rows[self.admin.email]["batch_count"], 1)
        self.assertTrue(rows[self.boss2.email]["is_superuser"])
        self.assertTrue(rows[self.admin.email]["name"])

    def test_a_users_batches_carry_counts_and_the_owner(self):
        r = call(views.TeamBulkUserBatchesView.as_view(), "get", "/t/", self.boss, email=self.admin.email)
        row = r.data["results"][0]
        self.assertEqual((row["total"], row["done"], row["working"], row["owner_email"]), (2, 1, 1, self.admin.email))
        self.assertTrue(row["owner_name"])
        other = call(views.TeamBulkUserBatchesView.as_view(), "get", "/t/", self.boss, email=self.boss2.email)
        self.assertEqual(other.data["count"], 1)

    def test_the_detail_shows_every_row_with_its_created_invoice_summary(self):
        r = call(views.TeamBulkBatchDetailView.as_view(), "get", "/t/", self.boss, batch_id=self.admin_batch.id)
        self.assertEqual(r.data["owner_email"], self.admin.email)
        self.assertEqual([i["status"] for i in r.data["items"]], ["done", "queued"])
        self.assertEqual(r.data["items"][0]["summary"]["grand_total"], "100.00")
        self.assertEqual(r.data["items"][0]["bill_number"], "BILL-2026-0001")

    def test_deleted_batches_stay_hidden_everywhere(self):
        BulkBatch.objects.filter(pk=self.admin_batch.pk).update(is_deleted=True)
        self.assertEqual(call(views.TeamBulkBatchDetailView.as_view(), "get", "/t/", self.boss, batch_id=self.admin_batch.id).status_code, 404)
        self.assertEqual(call(views.TeamBulkUserBatchesView.as_view(), "get", "/t/", self.boss, email=self.admin.email).data["count"], 0)
        owners = call(views.TeamBulkOwnersView.as_view(), "get", "/t/", self.boss).data["results"]
        self.assertEqual({o["email"] for o in owners}, {self.boss2.email})

    def test_a_team_read_never_repairs_or_changes_anything(self):
        old = timezone.now() - timedelta(seconds=settings.AGENT_BULK_ITEM_TIMEOUT_SECONDS + 900)
        BulkItem.objects.filter(batch=self.admin_batch, position=2).update(status="processing", started_at=old)
        r = call(views.TeamBulkBatchDetailView.as_view(), "get", "/t/", self.boss, batch_id=self.admin_batch.id)
        self.assertEqual(r.data["items"][1]["status"], "processing")             # the owner's own GET repairs it; this one must not
        self.assertEqual(BulkItem.objects.get(batch=self.admin_batch, position=2).status, "processing")

    def test_the_owners_own_endpoints_still_hide_other_peoples_batches(self):
        self.assertEqual(call(views.BulkBatchDetailView.as_view(), "get", "/b/x/", self.boss, batch_id=self.admin_batch.id).status_code, 404)
        self.assertEqual(call(views.BulkBatchListCreateView.as_view(), "get", "/b/", self.boss).data["count"], 0)

    def test_fixed_query_counts(self):
        for n in range(8):
            self.make_batch([f"p{n}-{i}" for i in range(10)])
        with CaptureQueriesContext(connection) as q:
            call(views.TeamBulkOwnersView.as_view(), "get", "/t/", self.boss)
        self.assertLessEqual(len(q), 4)
        with CaptureQueriesContext(connection) as q:
            r = call(views.TeamBulkUserBatchesView.as_view(), "get", "/t/", self.boss, email=self.admin.email)
        self.assertEqual(r.data["count"], 9)
        self.assertLessEqual(len(q), 4)                      # count + one grouped page; no per-batch owner / item queries
        with CaptureQueriesContext(connection) as q:
            call(views.TeamBulkBatchDetailView.as_view(), "get", "/t/", self.boss, batch_id=self.admin_batch.id)
        self.assertLessEqual(len(q), 5)                      # auth, batch+owner, its rows
