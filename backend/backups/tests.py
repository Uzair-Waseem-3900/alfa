import zipfile
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from users.models import User

from .models import BackupFlow, BackupHistory
from .services import collect_backup_data, run_local_backup
from .views import BackupHistoryListView


def make_admin(email="admin@example.com"):
    return User.objects.create_user(
        email=email, password="Adm1n-secret!", first_name="Admin",
        last_name="User", is_staff=True,
    )


def make_normal_user(email="normal@example.com"):
    return User.objects.create_user(
        email=email, password="N0rmal-secret!", first_name="Normal", last_name="User",
    )


class CollectBackupDataTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_full_collection_includes_every_row_and_excludes_own_bookkeeping(self):
        from cash_flow.services import create_expense, create_expense_category
        from data_entry.services import create_opening_cash
        from payment_methods.models import PaymentMethod

        create_opening_cash(amount=Decimal("100"), user=self.admin)
        cash = PaymentMethod.objects.get_or_create(name="Cash", defaults={"balance": Decimal("1000000")})[0]
        cat = create_expense_category(name="Utilities", user=self.admin)
        create_expense(
            name="Electricity", category_id=cat.id, amount=Decimal("10"),
            expense_date=timezone.now().date(), method_allocations=[(cash, Decimal("10"))], user=self.admin,
        )

        collected = collect_backup_data(since=None, as_of=timezone.now())
        labels = {m["label"] for m in collected["manifest_models"]}

        self.assertIn("users.user", labels)
        self.assertIn("cash_flow.expense", labels)
        # This app's own bookkeeping is never included in its own backup.
        self.assertNotIn("backups.backuphistory", labels)
        self.assertNotIn("backups.backupflow", labels)
        self.assertGreater(collected["row_count"], 0)

    def test_incremental_only_includes_rows_changed_since_watermark(self):
        from cash_flow.services import create_expense_category

        watermark = timezone.now()
        create_expense_category(name="After Watermark", user=self.admin)

        collected = collect_backup_data(since=watermark, as_of=timezone.now())
        cat_entry = next(
            (m for m in collected["manifest_models"] if m["label"] == "cash_flow.expensecategory"), None,
        )
        self.assertIsNotNone(cat_entry)
        self.assertEqual(cat_entry["count"], 1)


class LocalBackupTests(TestCase):
    def setUp(self):
        self.admin = make_admin()

    def test_full_backup_produces_zip_and_advances_watermark(self):
        zip_bytes, filename = run_local_backup(backup_type=BackupHistory.BackupType.FULL, user=self.admin)

        self.assertTrue(filename.startswith("backup-full-"))
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            self.assertEqual(len(zf.namelist()), 1)
            content = zf.read(zf.namelist()[0]).decode()
            self.assertIn("users.user", content)

        history = BackupHistory.objects.get()
        self.assertEqual(history.status, BackupHistory.Status.SUCCESS)
        self.assertEqual(history.destination, BackupHistory.Destination.LOCAL)
        self.assertIsNone(history.covers_from)
        self.assertGreater(history.row_count, 0)

        flow = BackupFlow.get_instance()
        self.assertIsNotNone(flow.local_last_backup_at)

    def test_incremental_with_no_prior_backup_degrades_to_full(self):
        _, filename = run_local_backup(backup_type=BackupHistory.BackupType.INCREMENTAL, user=self.admin)
        self.assertTrue(filename.startswith("backup-full-"))
        history = BackupHistory.objects.get()
        self.assertEqual(history.backup_type, BackupHistory.BackupType.FULL)
        self.assertIsNone(history.covers_from)

    def test_second_incremental_only_covers_since_last_watermark(self):
        run_local_backup(backup_type=BackupHistory.BackupType.FULL, user=self.admin)
        first_watermark = BackupFlow.get_instance().local_last_backup_at

        _, filename = run_local_backup(backup_type=BackupHistory.BackupType.INCREMENTAL, user=self.admin)
        self.assertTrue(filename.startswith("backup-incremental-"))

        history = BackupHistory.objects.order_by("-created_at").first()
        self.assertEqual(history.backup_type, BackupHistory.BackupType.INCREMENTAL)
        self.assertEqual(history.covers_from, first_watermark)

    def test_failure_is_recorded_and_watermark_is_not_advanced(self):
        with patch("backups.services.collect_backup_data", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                run_local_backup(backup_type=BackupHistory.BackupType.FULL, user=self.admin)

        history = BackupHistory.objects.get()
        self.assertEqual(history.status, BackupHistory.Status.FAILED)
        self.assertEqual(history.error_message, "boom")
        self.assertIsNone(BackupFlow.get_instance().local_last_backup_at)


class BackupHistoryListPermissionTests(TestCase):
    def test_admin_sees_history_newest_first(self):
        admin = make_admin()
        run_local_backup(backup_type=BackupHistory.BackupType.FULL, user=admin)
        run_local_backup(backup_type=BackupHistory.BackupType.INCREMENTAL, user=admin)

        request = APIRequestFactory().get("/api/backups/history/")
        force_authenticate(request, user=admin)
        response = BackupHistoryListView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["results"][0]["backup_type"], "incremental")

    def test_normal_user_gets_403(self):
        request = APIRequestFactory().get("/api/backups/history/")
        force_authenticate(request, user=make_normal_user())
        response = BackupHistoryListView.as_view()(request)
        self.assertEqual(response.status_code, 403)
