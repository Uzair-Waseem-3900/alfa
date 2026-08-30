from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from backend.settings import DATA_GMAIL

MIGRATION_USER_EMAIL = DATA_GMAIL
if not MIGRATION_USER_EMAIL:
    raise CommandError("DATA_GMAIL is not set in settings.py")

# Order matters: Product depends on Category/Shelf, and Ledger depends on
# Supplier, already existing in the new DB (looked up by name/code).
TABLE_ORDER = ["category", "shelf", "supplier", "product", "ledger"]


class Command(BaseCommand):
    help = (
        "One-off/reusable import of lookup data (Category, Shelf, Supplier, Product) "
        "and supplier ledgers (SupplierLedger + SupplierLedgerEntry) from the legacy DB "
        "(settings.DATABASES['legacy']) into the current default DB. Schema/relationships "
        "are identical between the two DBs for these tables. Safe to re-run: existing rows "
        "are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--tables", nargs="+", choices=TABLE_ORDER, default=None,
            help="Subset of tables to import (default: all four, in dependency order).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would be created/skipped without writing anything.",
        )

    def handle(self, *args, **options):
        from purchases.models import Category, Shelf, Supplier, Product

        requested = set(options["tables"] or TABLE_ORDER)
        dry_run = options["dry_run"]

        User = get_user_model()
        try:
            migration_user = User.objects.get(email=MIGRATION_USER_EMAIL)
        except User.DoesNotExist:
            raise CommandError(
                f"Migration attribution user '{MIGRATION_USER_EMAIL}' does not exist "
                f"in the target database. Create this user first, then re-run."
            )

        summary = {}
        # In --dry-run, category/shelf rows are never actually written, so the
        # product step (which looks them up by name) needs to know what this
        # same run *would have* created, on top of what already exists.
        dry_run_names = {"category": set(), "shelf": set()}

        if "category" in requested:
            summary["category"] = self._import_simple(
                Category, "name", migration_user, dry_run, dry_run_names["category"],
            )
        if "shelf" in requested:
            summary["shelf"] = self._import_simple(
                Shelf, "name", migration_user, dry_run, dry_run_names["shelf"],
            )
        if "supplier" in requested:
            summary["supplier"] = self._import_supplier(Supplier, migration_user, dry_run)
        if "product" in requested:
            summary["product"] = self._import_product(
                Product, Category, migration_user, dry_run, dry_run_names,
            )
        if "ledger" in requested:
            summary["ledger"] = self._import_ledger(Supplier, migration_user, dry_run)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Import summary" + (" (dry run)" if dry_run else "") + ":"))
        for table, counts in summary.items():
            self.stdout.write(
                f"  {table}: created={counts['created']} skipped={counts['skipped']} errors={counts['errors']}"
            )

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _stamp(self, model, pk, row):
        """created_at/updated_at are auto_now_add/auto_now — .create() always
        overwrites them to "now", so restore the legacy timestamps afterward."""
        model.all_objects.filter(pk=pk).update(
            created_at=row.created_at, updated_at=row.updated_at,
        )

    def _import_simple(self, model, unique_field, migration_user, dry_run, dry_run_names=None):
        created = skipped = errors = 0
        legacy_rows = model.all_objects.using("legacy").all()

        for row in legacy_rows:
            lookup = {unique_field: getattr(row, unique_field)}
            if model.all_objects.filter(**lookup).exists():
                skipped += 1
                continue

            if dry_run:
                created += 1
                if dry_run_names is not None:
                    dry_run_names.add(getattr(row, unique_field))
                continue

            try:
                with transaction.atomic():
                    new_row = model.all_objects.create(
                        **{unique_field: getattr(row, unique_field)},
                        description=row.description,
                        created_by=migration_user,
                        updated_by=migration_user,
                        deleted_by=migration_user if row.is_deleted else None,
                        deleted_at=row.deleted_at,
                        is_deleted=row.is_deleted,
                    )
                    self._stamp(model, new_row.pk, row)
                created += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.WARNING(
                    f"  [{model.__name__}] failed to import '{getattr(row, unique_field)}': {exc}"
                ))

        return {"created": created, "skipped": skipped, "errors": errors}

    def _import_ledger(self, Supplier, migration_user, dry_run):
        from ledger.models import SupplierLedger, SupplierLedgerEntry
        from ledger.services import (
            _get_year_month, _recalculate_snapshots_from, create_ledger_for_supplier,
        )

        created = skipped = errors = 0
        entries_created = entries_skipped = 0

        # Legacy schema predates is_deleted/deleted_at/deleted_by on
        # SupplierLedger (this run is what introduces those fields) — restrict
        # the SELECT to columns that actually exist in the legacy table.
        legacy_ledgers = SupplierLedger.objects.using("legacy").values(
            "id", "supplier_code", "created_at",
        )

        for legacy_ledger in legacy_ledgers:
            new_supplier = Supplier.all_objects.filter(code=legacy_ledger["supplier_code"]).first()
            if new_supplier is None:
                errors += 1
                self.stderr.write(self.style.WARNING(
                    f"  [Ledger] skipping '{legacy_ledger['supplier_code']}': supplier not found "
                    f"in target DB (import supplier first)"
                ))
                continue

            legacy_entries = SupplierLedgerEntry.objects.using("legacy").filter(
                ledger_id=legacy_ledger["id"],
            ).order_by("date", "created_at")
            existing_ledger = SupplierLedger.objects.filter(supplier=new_supplier).first()

            if dry_run:
                for entry in legacy_entries:
                    already = existing_ledger and SupplierLedgerEntry.objects.filter(
                        ledger=existing_ledger, reference=entry.reference,
                        entry_type=entry.entry_type, date=entry.date,
                    ).exists()
                    entries_skipped += 1 if already else 0
                    entries_created += 0 if already else 1
                created += 1
                continue

            try:
                with transaction.atomic():
                    new_ledger = create_ledger_for_supplier(supplier=new_supplier)
                    earliest_affected_month = None

                    for entry in legacy_entries:
                        if SupplierLedgerEntry.objects.filter(
                            ledger=new_ledger, reference=entry.reference,
                            entry_type=entry.entry_type, date=entry.date,
                        ).exists():
                            entries_skipped += 1
                            continue

                        # Source order/payment/return links aren't part of this
                        # migration — imported entries carry the historical
                        # amounts/dates only, links left null.
                        new_entry = SupplierLedgerEntry.objects.create(
                            ledger=new_ledger,
                            entry_type=entry.entry_type,
                            date=entry.date,
                            details=entry.details,
                            reference=entry.reference,
                            debit=entry.debit,
                            credit=entry.credit,
                            created_by=migration_user,
                        )
                        SupplierLedgerEntry.objects.filter(pk=new_entry.pk).update(
                            created_at=entry.created_at,
                        )
                        entries_created += 1
                        ym = _get_year_month(entry.date)
                        if earliest_affected_month is None or ym < earliest_affected_month:
                            earliest_affected_month = ym

                    if earliest_affected_month is not None:
                        _recalculate_snapshots_from(new_ledger, earliest_affected_month)

                created += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.WARNING(
                    f"  [Ledger] failed to import '{legacy_ledger['supplier_code']}': {exc}"
                ))

        self.stdout.write(f"    ledger entries: created={entries_created} skipped={entries_skipped}")
        return {"created": created, "skipped": skipped, "errors": errors}

    def _import_supplier(self, Supplier, migration_user, dry_run):
        created = skipped = errors = 0
        legacy_rows = Supplier.all_objects.using("legacy").all()

        for row in legacy_rows:
            if Supplier.all_objects.filter(code=row.code).exists():
                skipped += 1
                continue

            if dry_run:
                created += 1
                continue

            try:
                with transaction.atomic():
                    new_row = Supplier.all_objects.create(
                        name=row.name,
                        code=row.code,
                        created_by=migration_user,
                        updated_by=migration_user,
                        deleted_by=migration_user if row.is_deleted else None,
                        deleted_at=row.deleted_at,
                        is_deleted=row.is_deleted,
                    )
                    self._stamp(Supplier, new_row.pk, row)
                created += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.WARNING(
                    f"  [Supplier] failed to import '{row.code}': {exc}"
                ))

        return {"created": created, "skipped": skipped, "errors": errors}

    def _import_product(self, Product, Category, migration_user, dry_run, dry_run_names=None):
        # NOTE: Product.shelf was removed (shelves are now decoupled from
        # products — see purchases.ShelfStock). This import used to also
        # look up the legacy row's shelf and link it via Product.shelf;
        # that product-shelf-linking logic has been removed. The Shelf
        # lookup-table import itself (TABLE_ORDER "shelf" step, _import_simple)
        # is untouched — it's still a valid standalone lookup table.
        created = skipped = errors = 0
        legacy_rows = Product.all_objects.using("legacy").select_related("category").all()
        dry_run_names = dry_run_names or {"category": set(), "shelf": set()}

        for row in legacy_rows:
            if Product.all_objects.filter(code=row.code).exists():
                skipped += 1
                continue

            new_category = Category.all_objects.filter(name=row.category.name).first()
            category_ok = new_category is not None or row.category.name in dry_run_names["category"]
            if not category_ok:
                errors += 1
                self.stderr.write(self.style.WARNING(
                    f"  [Product] skipping '{row.code}': missing category '{row.category.name}' "
                    f"in target DB (import category first)"
                ))
                continue

            if dry_run:
                created += 1
                continue

            try:
                with transaction.atomic():
                    new_row = Product.all_objects.create(
                        name=row.name,
                        code=row.code,
                        category=new_category,
                        created_by=migration_user,
                        updated_by=migration_user,
                        deleted_by=migration_user if row.is_deleted else None,
                        deleted_at=row.deleted_at,
                        is_deleted=row.is_deleted,
                    )
                    self._stamp(Product, new_row.pk, row)
                created += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.WARNING(
                    f"  [Product] failed to import '{row.code}': {exc}"
                ))

        return {"created": created, "skipped": skipped, "errors": errors}
