import re
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction
from django.db.models import Sum

CODE_PATTERN = re.compile(r"^(?P<prefix>[^-]+)-(?P<link>FSD|OS)-(?P<suffix>.+)$", re.IGNORECASE)

SEED_SALES_MEN = [
    {"name": "sale_man_1", "code": "SM1", "link": "FSD"},
    {"name": "sale_man_2", "code": "SM2", "link": "OS"},
]


def _clean_suffix(raw_suffix: str) -> str:
    """
    The suffix segment is captured greedily (everything after prefix-link),
    so real data with a stray hyphen inside it (e.g. 'CUS-OS-786-155',
    originally meant as one code) comes through as '786-155'. Every hyphen
    inside the suffix is stripped so the stored code_suffix and composed
    code always read as one contiguous token, e.g. '786155'.
    """
    return raw_suffix.replace("-", "")


class Command(BaseCommand):
    """
    One-off setup + data-fix command for the sales_man app.

    1. Creates SalesMan 'sale_man_1'/'sale_man_2' (idempotent, get_or_create
       by code) and their SalesManLinkName 'FSD'/'OS' (idempotent, by name).
    2. Scans every non-deleted Customer whose `code` matches
       PREFIX-<FSD|OS>-suffix (case-insensitive). The prefix is rewritten to
       settings.CUSTOMER_PREFIX and any stray hyphen(s) inside the suffix are
       stripped (see _clean_suffix) — the link segment and the suffix's own
       characters are otherwise never touched. This re-normalizes on EVERY
       run, not just customers whose prefix is currently wrong, so a
       customer already sitting at 'ALFA-OS-786-155' from an earlier run
       still gets cleaned up to 'ALFA-OS-786155' on a re-run. Matching
       customers are assigned to the corresponding sales man/link name.
    3. Any customer whose code does NOT match the pattern is reported at the
       TOP of the output as malformed, needing manual attention, and is
       never touched.
    4. A fix that would collide with another customer's existing code (real
       production data can have e.g. both 'ALF-FSD-786155' and
       'ALFA-FSD-786155' as separate rows) is reported separately and
       skipped, rather than crashing/rolling back the whole batch.
    5. Recomputes total_customers/total_outstanding for both sales men from
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
        code_fixes = []       # (customer, current_code, target_code, clean_suffix)
        code_collisions = []  # (customer, current_code, target_code)
        assignments = []

        customers = Customer.objects.filter(is_deleted=False).select_related(
            "sales_man_link_name",
        ).order_by("id")

        # Every code currently in use — used to detect a fix that would
        # collide with another customer's existing code (real production
        # data has both 'ALF-FSD-123' and 'ALFA-FSD-123' as SEPARATE rows,
        # e.g. an old typo'd prefix that was never cleaned up). Updated as
        # we go so two fixes in THIS SAME batch that would land on the same
        # target code are also caught, not just collisions against rows
        # that were already correct.
        codes_in_use = {c.code.upper() for c in customers}

        for customer in customers:
            match = CODE_PATTERN.match(customer.code)
            if not match:
                malformed.append(customer)
                continue

            link_key = match.group("link").upper()
            clean_suffix = _clean_suffix(match.group("suffix"))
            link_name = link_name_objs.get(link_key)

            target_code = f"{prefix}-{link_key}-{clean_suffix}".upper()
            if target_code != customer.code.upper():
                if target_code in codes_in_use:
                    code_collisions.append((customer, customer.code, target_code))
                else:
                    code_fixes.append((customer, customer.code, target_code, clean_suffix))
                    codes_in_use.discard(customer.code.upper())
                    codes_in_use.add(target_code)

            current_link = customer.sales_man_link_name
            already_assigned = (
                current_link is not None
                and current_link.name.upper() == link_key
                and customer.sales_man_id == link_name.sales_man_id
                and customer.code_suffix == clean_suffix
            )
            if link_name and not already_assigned:
                assignments.append((customer, link_name, clean_suffix))

        # ------------------------------------------------------------
        # Report: totals first, then malformed codes (fix these manually
        # before anything else), then what will actually change.
        # ------------------------------------------------------------
        total_customers = len(customers)  # queryset already fully evaluated by the loop above — no extra query
        convertible = total_customers - len(malformed) - len(code_collisions)
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\n=== Summary: {total_customers} customer(s) scanned — "
            f"{convertible} match the expected code structure and can be "
            f"converted with no error, {len(malformed)} malformed, "
            f"{len(code_collisions)} blocked by a code collision ==="
        ))

        self.stdout.write(self.style.WARNING(
            f"\n=== {len(malformed)} customer(s) with a code NOT matching "
            f"'<prefix>-<FSD|OS>-<suffix>' — fix these manually first ==="
        ))
        for customer in malformed:
            self.stdout.write(f"  id={customer.id} code={customer.code!r} name={customer.name!r}")

        self.stdout.write(self.style.WARNING(
            f"\n=== {len(code_collisions)} customer(s) whose fixed code would "
            f"COLLIDE with another customer's existing code — fix these manually "
            f"first (likely a duplicate/typo'd record) ==="
        ))
        for customer, current_code, target_code in code_collisions:
            self.stdout.write(
                f"  id={customer.id} {current_code!r} -> would become {target_code!r}, "
                f"but that code is already used by another customer"
            )

        self.stdout.write(f"\n=== {len(code_fixes)} customer(s) need their code fixed to match {prefix!r}-<link>-<suffix> ===")
        for customer, current_code, target_code, _clean_suffix_value in code_fixes:
            self.stdout.write(f"  id={customer.id} {current_code!r} -> {target_code!r}")

        self.stdout.write(f"\n=== {len(assignments)} customer(s) will be (re)assigned to a sales man ===")
        for customer, link_name, clean_suffix in assignments:
            self.stdout.write(
                f"  id={customer.id} {customer.code!r} -> link={link_name.name} "
                f"sales_man={link_name.sales_man.name}"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING("\n--dry-run: no changes were made."))
            return

        # ------------------------------------------------------------
        # Step 3: apply code fixes + assignments
        # ------------------------------------------------------------
        skipped_code_fixes = []
        with transaction.atomic():
            fixed_ids = set()
            for customer, current_code, target_code, clean_suffix in code_fixes:
                # The proactive collision check above already rules out the
                # vast majority of cases — this savepoint is a defense-in-
                # depth net so an edge case it missed (e.g. a race with
                # another process writing concurrently) skips just this one
                # row instead of rolling back every fix already applied in
                # this run.
                try:
                    with transaction.atomic():
                        customer.code = target_code
                        customer.save(update_fields=["code"])
                except IntegrityError:
                    skipped_code_fixes.append((customer, target_code))
                    continue
                fixed_ids.add(customer.id)

            for customer, link_name, clean_suffix in assignments:
                # Only needed for a customer that ALSO had its code fixed
                # above — its in-memory `code` was just overwritten there,
                # so this avoids clobbering that with the stale pre-fix
                # value. A customer with no code fix already has the
                # correct `code` in memory, no extra query needed.
                if customer.id in fixed_ids:
                    customer.refresh_from_db(fields=["code"])
                customer.sales_man_link_name = link_name
                customer.sales_man = link_name.sales_man
                customer.code_suffix = clean_suffix
                customer.save(update_fields=["sales_man_link_name", "sales_man", "code_suffix"])

            # Step 5: idempotent full recompute of both stats fields.
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

        if skipped_code_fixes:
            self.stdout.write(self.style.WARNING(
                f"\n{len(skipped_code_fixes)} code fix(es) were skipped at write "
                f"time due to an unexpected code collision — investigate manually:"
            ))
            for customer, target_code in skipped_code_fixes:
                self.stdout.write(f"  id={customer.id} -> would become {target_code!r}")

        self.stdout.write(self.style.SUCCESS("\nDone."))
