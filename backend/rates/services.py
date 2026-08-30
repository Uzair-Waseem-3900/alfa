from decimal import Decimal

from django.db import IntegrityError, transaction

from purchases.models import Product
from purchases.selectors import get_product_by_id

from .models import ProductRate, ProductRateHistory, UnpricedProduct
from .selectors import get_rate_by_id


# ---------------------------------------------------------------------------
# Internal helper — always called after any price change
# ---------------------------------------------------------------------------

def _log_rate_history(*, product: Product, selling_price: Decimal, user, note: str = "") -> None:
    """
    Append a new row to ProductRateHistory.
    Private — only called from within this service module.
    This is the single place responsible for keeping the audit log intact.
    """
    ProductRateHistory.objects.create(
        product=product,
        selling_price=selling_price,
        changed_by=user,
        note=note,
    )


# ---------------------------------------------------------------------------
# Unpriced-products queue — kept in sync explicitly by whoever changes
# pricing status (see rates.models.UnpricedProduct for the full picture).
# purchases.services.create_product()/delete_product() call these via a
# lazy import (mirrors the lazy purchases-model imports already used
# elsewhere in this app) so purchases stays unaware rates exists.
# ---------------------------------------------------------------------------

def add_to_unpriced_queue(product: Product) -> None:
    UnpricedProduct.objects.get_or_create(product=product)


def remove_from_unpriced_queue(product: Product) -> None:
    UnpricedProduct.objects.filter(product=product).delete()


# ---------------------------------------------------------------------------
# Public services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_rate(*, product_id: int, selling_price: Decimal, user, note: str = "") -> ProductRate:
    """
    Create a new ProductRate for a product.
    Raises ValidationError if a rate already exists for this product
    (use update_rate instead).

    Atomic: the rate row and its first history entry are all-or-nothing —
    billing snapshots prices FROM the history table, so a rate must never
    exist without its matching history row.
    """
    from rest_framework.exceptions import ValidationError

    product = get_product_by_id(product_id)

    duplicate_error = ValidationError(
        {"product": f"A rate already exists for '{product.name}'. Use PATCH to update it."}
    )

    if ProductRate.objects.filter(product=product).exists():
        raise duplicate_error

    try:
        # The exists() pre-check can race a concurrent create — the OneToOne
        # constraint is the real guard, so a duplicate insert must surface as
        # the same clean 400, not a 500. atomic() keeps the failed insert on
        # a savepoint so the surrounding transaction stays usable.
        with transaction.atomic():
            rate = ProductRate.objects.create(
                product=product,
                selling_price=selling_price,
                created_by=user,
                updated_by=user,
            )
    except IntegrityError:
        raise duplicate_error

    # Log the initial price setting as first history entry
    _log_rate_history(product=product, selling_price=selling_price, user=user, note=note or "Initial price set.")
    remove_from_unpriced_queue(product)
    return rate


@transaction.atomic
def update_rate(*, pk: int, selling_price: Decimal, user, note: str = "") -> ProductRate:
    """
    Update the current selling price of an existing ProductRate.
    Always logs the change into ProductRateHistory in the same transaction —
    a price change without its history row would make billing (which
    snapshots prices from history) disagree with the rates page.
    """
    rate = get_rate_by_id(pk)

    rate.selling_price = selling_price
    rate.updated_by = user
    rate.save(update_fields=["selling_price", "updated_by", "updated_at"])

    _log_rate_history(
        product=rate.product,
        selling_price=selling_price,
        user=user,
        note=note,
    )
    return rate


def update_rate_by_product(*, product_id: int, selling_price: Decimal, user, note: str = "") -> ProductRate:
    """
    Convenience service: update rate using product_id instead of rate pk.
    Useful for bulk update flows where only product IDs are available.
    Delegates to update_rate to keep logic DRY.
    """
    from .selectors import get_rate_by_product_id
    rate = get_rate_by_product_id(product_id)
    return update_rate(pk=rate.pk, selling_price=selling_price, user=user, note=note)