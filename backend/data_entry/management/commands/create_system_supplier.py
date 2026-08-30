from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates the system 'Opening Stock' supplier (code SYS-OPENING) used for opening stock data entry."

    def handle(self, *args, **options):
        from purchases.models import Supplier

        if Supplier.all_objects.filter(code="SYS-OPENING").exists():
            self.stdout.write(self.style.WARNING("System supplier 'SYS-OPENING' already exists. Skipping."))
            return

        # Reuse the supplier service so the ledger is auto-created too.
        from purchases.services import create_supplier
        create_supplier(name="Opening Stock", code="SYS-OPENING", user=None)
        self.stdout.write(self.style.SUCCESS("Created system supplier 'Opening Stock' (SYS-OPENING)."))
