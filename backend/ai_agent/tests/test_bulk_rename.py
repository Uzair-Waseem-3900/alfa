"""Renaming a bulk batch."""
from django.core.cache import cache
from django.test import TestCase

from ai_agent import views
from ai_agent.models import BulkBatch

from .helpers import make_admin, make_plain_user
from .test_api import call
from .test_bulk import BulkWorld


class RenameBulkBatchTests(BulkWorld, TestCase):
    def setUp(self):
        cache.clear()
        self.build_world()
        self.other = make_admin("admin2@example.com")
        self.batch = self.make_batch(["a", "b"])

    def rename(self, title, user=None, batch=None):
        return call(views.BulkBatchDetailView.as_view(), "patch", "/b/x/", user or self.admin,
                    {"title": title}, batch_id=(batch or self.batch).id)

    def test_rename_trims_saves_and_shows_in_detail_and_list(self):
        r = self.rename("  Faisalabad orders  ")
        self.assertEqual((r.status_code, r.data["title"]), (200, "Faisalabad orders"))
        self.assertEqual(len(r.data["items"]), 2)                                       # the full batch comes back
        self.assertEqual(BulkBatch.objects.get(pk=self.batch.pk).title, "Faisalabad orders")
        listed = call(views.BulkBatchListCreateView.as_view(), "get", "/b/", self.admin).data["results"][0]
        self.assertEqual(listed["title"], "Faisalabad orders")

    def test_a_new_batch_has_no_title_until_renamed(self):
        detail = call(views.BulkBatchDetailView.as_view(), "get", "/b/x/", self.admin, batch_id=self.batch.id)
        self.assertEqual(detail.data["title"], "")

    def test_blank_and_too_long_titles_are_refused(self):
        self.assertEqual(self.rename("   ").status_code, 400)
        self.assertEqual(self.rename("x" * 121).status_code, 400)
        self.assertEqual(BulkBatch.objects.get(pk=self.batch.pk).title, "")

    def test_only_the_owner_can_rename(self):
        self.assertEqual(self.rename("hijack", user=self.other).status_code, 404)
        self.assertEqual(self.rename("x", user=make_plain_user()).status_code, 403)
        self.assertEqual(BulkBatch.objects.get(pk=self.batch.pk).title, "")

    def test_a_deleted_batch_cannot_be_renamed_and_put_is_not_allowed(self):
        self.assertEqual(call(views.BulkBatchDetailView.as_view(), "put", "/b/x/", self.admin, {"title": "x"}, batch_id=self.batch.id).status_code, 405)
        BulkBatch.objects.filter(pk=self.batch.pk).update(is_deleted=True)
        self.assertEqual(self.rename("late").status_code, 404)

    def test_renaming_does_not_touch_the_rows(self):
        before = list(self.batch.items.values_list("status", "attempts"))
        self.rename("Renamed")
        self.assertEqual(list(self.batch.items.values_list("status", "attempts")), before)
