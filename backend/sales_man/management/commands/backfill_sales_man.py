import re
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

CODE_PATTERN = re.compile(r"^(?P<prefix>[^-]+)-(?P<link>FSD|OS)-(?P<suffix>.+)$", re.IGNORECASE)

SEED_SALES_MEN = [
    {"name": "sale_man_1", "code": "SM1", "link": "FSD"},
    {"name": "sale_man_2", "code": "SM2", "link": "OS"},
]


class Command(BaseCommand):
    """
    One-off setup + data-fix command for the sales_man app.

    1. Creates SalesMan 'sale_man_1'/'sale_man_2' (idempotent, get_or_create
       by code) and their SalesManLinkName 'FSD'/'OS' (idempotent, by name).
    2. Scans every non-deleted Customer whose `code` matches
       PREFIX-<FSD|OS>-suffix (case-insensitive). Only the PREFIX segment is
       ever rewritten (to settings.CUSTOMER_PREFIX) — the link segment and
       suffix are never touched, per the project's explicit instruction not
       to change the code's meaning, only its prefix. Matching customers are
       assigned to the corresponding sales man/link name.
    3. Any customer whose code does NOT match the pattern is reported at the
       TOP of the output as malformed, needing manual attention, and is
       never touched.
    4. Recomputes total_customers/total_outstanding for both sales men from
       scratch (idempotent — safe to re-run any number of times).

    Default run WRITES. Pass --dry-run to only print the report without
    changing anything.
    """

    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report only — make no database changes.",
        )

    def handle(self, *args, **options):
        from billing.models import Customer, Invoice
        from sales_man.models import SalesMan, SalesManLinkName

        dry_run = options["dry_run"]
        prefix = settings.CUSTOMER_PREFIX
        if not prefix:
            self.stderr.write(self.style.ERROR(
                "CUSTOMER_PREFIX is not set in the environment/.env — aborting."
            ))
            return

        # ------------------------------------------------------------
        # Step 1: seed sales men + link names (idempotent)
        # ------------------------------------------------------------
        link_name_objs = {}
        if dry_run:
            # Read-only: use whatever already exists, or an UNSAVED instance
            # (never .create()'d) purely so the report below can show what
            # WOULD be created/assigned, without writing anything.
            for seed in SEED_SALES_MEN:
                sales_man = SalesMan.objects.filter(code=seed["code"]).first() \
                    or SalesMan(code=seed["code"], name=seed["name"])
                link_name = SalesManLinkName.objects.filter(name=seed["link"]).first() \
                    or SalesManLinkName(name=seed["link"], sales_man=sales_man)
                link_name_objs[seed["link"]] = link_name
        else:
            with transaction.atomic():
                for seed in SEED_SALES_MEN:
                    sales_man, _ = SalesMan.objects.get_or_create(
                        code=seed["code"], defaults={"name": seed["name"]},
                    )
                    link_name, _ = SalesManLinkName.objects.get_or_create(
                        name=seed["link"], defaults={"sales_man": sales_man},
                    )
                    link_name_objs[seed["link"]] = link_name

        # ------------------------------------------------------------
        # Step 2: scan customers
        # ------------------------------------------------------------
        malformed = []
        prefix_fixes = []
        assignments = []

        customers = Customer.objects.filter(is_deleted=False).select_related(
            "sales_man_link_name",
        ).order_by("id")
        for customer in customers:
            match = CODE_PATTERN.match(customer.code)
            if not match:
                malformed.append(customer)
                continue

            found_prefix = match.group("prefix")
            link_key = match.group("link").upper()
            suffix = match.group("suffix")
            link_name = link_name_objs.get(link_key)

            if found_prefix != prefix:
                prefix_fixes.append((customer, found_prefix, prefix))

            current_link = customer.sales_man_link_name
            already_assigned = (
                current_link is not None
                and current_link.name.upper() == link_key
                and customer.sales_man_id == link_name.sales_man_id
            )
            if link_name and not already_assigned:
                assignments.append((customer, link_name, suffix))

        # ------------------------------------------------------------
        # Report: totals first, then malformed codes (fix these manually
        # before anything else), then what will actually change.
        # ------------------------------------------------------------
        total_customers = len(customers)  # queryset already fully evaluated by the loop above — no extra query
        convertible = total_customers - len(malformed)
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== Summary: {total_customers} customer(s) scanned — "
            f"{convertible} match the expected code structure and can be "
            f"converted with no error, {len(malformed)} do not ==="
        ))

        self.stdout.write(self.style.WARNING(
            f"\n=== {len(malformed)} customer(s) with a code NOT matching "
            f"'<prefix>-<FSD|OS>-<suffix>' — fix these manually first ==="
        ))
        for customer in malformed:
            self.stdout.write(f"  id={customer.id} code={customer.code!r} name={customer.name!r}")

        self.stdout.write(f"\n=== {len(prefix_fixes)} customer(s) need their code prefix fixed to {prefix!r} ===")
        for customer, old_prefix, new_prefix in prefix_fixes:
            self.stdout.write(f"  id={customer.id} {customer.code!r} -> prefix {old_prefix!r} -> {new_prefix!r}")

        self.stdout.write(f"\n=== {len(assignments)} customer(s) will be (re)assigned to a sales man ===")
        for customer, link_name, suffix in assignments:
            self.stdout.write(
                f"  id={customer.id} {customer.code!r} -> link={link_name.name} "
                f"sales_man={link_name.sales_man.name}"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("\n--dry-run: no changes were made."))
            return

        # ------------------------------------------------------------
        # Step 3: apply prefix fixes + assignments
        # ------------------------------------------------------------
        with transaction.atomic():
            prefix_fixed_ids = set()
            for customer, old_prefix, new_prefix in prefix_fixes:
                match = CODE_PATTERN.match(customer.code)
                customer.code = f"{new_prefix}-{match.group('link').upper()}-{match.group('suffix')}"
                customer.save(update_fields=["code"])
                prefix_fixed_ids.add(customer.id)

            for customer, link_name, suffix in assignments:
                # Only needed for a customer that ALSO had its prefix fixed
                # above — its in-memory `code` was just overwritten there,
                # so this avoids clobbering that with the stale pre-fix
                # value. A customer with no prefix fix already has the
                # correct `code` in memory, no extra query needed.
                if customer.id in prefix_fixed_ids:
                    customer.refresh_from_db(fields=["code"])
                customer.sales_man_link_name = link_name
                customer.sales_man = link_name.sales_man
                customer.code_suffix = suffix
                customer.save(update_fields=["sales_man_link_name", "sales_man", "code_suffix"])

            # Step 4: idempotent full recompute of both stats fields.
            for seed in SEED_SALES_MEN:
                sales_man = SalesMan.objects.get(code=seed["code"])
                total_customers = Customer.objects.filter(
                    sales_man_id=sales_man.id, is_deleted=False,
                ).count()
                total_outstanding = Invoice.objects.filter(
                    customer__sales_man_id=sales_man.id, is_deleted=False,
                ).exclude(status=Invoice.Status.DRAFT).aggregate(
                    total=Sum("credit_outstanding"),
                )["total"] or Decimal("0")
                sales_man.total_customers = total_customers
                sales_man.total_outstanding = total_outstanding
                sales_man.save(update_fields=["total_customers", "total_outstanding"])
                self.stdout.write(self.style.SUCCESS(
                    f"{sales_man.name}: total_customers={total_customers} "
                    f"total_outstanding={total_outstanding}"
                ))

        self.stdout.write(self.style.SUCCESS("\nDone."))
