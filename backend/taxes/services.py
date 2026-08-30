from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import TaxFlow, TaxPayment, WHTPayment


# ---------------------------------------------------------------------------
# Internal atomic TaxFlow adjuster — NEVER call from outside this module
# ---------------------------------------------------------------------------

def _adjust_taxflow(
    *,
    total_input_tax_paid_delta              : Decimal = Decimal("0"),
    total_output_tax_collected_delta        : Decimal = Decimal("0"),
    total_sales_tax_paid_delta              : Decimal = Decimal("0"),
    total_wht_withheld_from_suppliers_delta : Decimal = Decimal("0"),
    total_wht_withheld_by_customers_delta   : Decimal = Decimal("0"),
    total_wht_paid_delta                    : Decimal = Decimal("0"),
    user,
) -> TaxFlow:
    """
    Atomically adjusts the TaxFlow singleton by the given deltas, then
    recalculates and SAVES the two derived fields (net_sales_tax_payable,
    sales_tax_outstanding) so nothing downstream ever has to sum rows at
    request time. Positive delta = increase. Negative delta = decrease.
    This is the ONLY function that writes to TaxFlow.
    """
    with transaction.atomic():
        tf = TaxFlow.objects.select_for_update().get_or_create(pk=1)[0]

        tf.total_input_tax_paid = max(
            Decimal("0"), tf.total_input_tax_paid + total_input_tax_paid_delta
        )
        tf.total_output_tax_collected = max(
            Decimal("0"), tf.total_output_tax_collected + total_output_tax_collected_delta
        )
        tf.total_sales_tax_paid = max(
            Decimal("0"), tf.total_sales_tax_paid + total_sales_tax_paid_delta
        )
        tf.total_wht_withheld_from_suppliers = max(
            Decimal("0"),
            tf.total_wht_withheld_from_suppliers + total_wht_withheld_from_suppliers_delta,
        )
        tf.total_wht_withheld_by_customers = max(
            Decimal("0"),
            tf.total_wht_withheld_by_customers + total_wht_withheld_by_customers_delta,
        )
        tf.total_wht_paid = max(
            Decimal("0"), tf.total_wht_paid + total_wht_paid_delta
        )

        # Derived fields — recomputed and stored on every sync, not on read.
        tf.net_sales_tax_payable = tf.total_output_tax_collected - tf.total_input_tax_paid
        tf.sales_tax_outstanding = max(
            Decimal("0"), tf.net_sales_tax_payable - tf.total_sales_tax_paid
        )
        # wht_outstanding is NEVER netted against total_wht_withheld_by_customers —
        # that's a different taxpayer's obligation (WHT deposited by customers on
        # the store's behalf), not something the store can apply against its own
        # deposit duty for tax withheld from suppliers. See TaxFlow docstring.
        tf.wht_outstanding = max(
            Decimal("0"), tf.total_wht_withheld_from_suppliers - tf.total_wht_paid
        )

        tf.last_updated_by = user
        tf.save()
        return tf


# ---------------------------------------------------------------------------
# Public sync functions — called by purchases and billing apps
# ---------------------------------------------------------------------------

def sync_purchase_tax(*, gst_amount: Decimal, wht_amount: Decimal, user) -> None:
    """
    Called when a real (non-data-entry) purchase order is confirmed.
    gst_amount -> total_input_tax_paid (GST you paid to this supplier)
    wht_amount -> total_wht_withheld_from_suppliers (tax you deducted from
                  the supplier's payment — informational only, see README)
    """
    _adjust_taxflow(
        total_input_tax_paid_delta              = +gst_amount,
        total_wht_withheld_from_suppliers_delta = +wht_amount,
        user=user,
    )


def sync_invoice_tax(*, gst_amount: Decimal, wht_amount: Decimal, user) -> None:
    """
    Called when a real (non-data-entry) invoice is confirmed.
    gst_amount -> total_output_tax_collected (GST you charged this customer)
    wht_amount -> total_wht_withheld_by_customers (tax the customer deducted
                  from what they owe you — informational only, see README)
    """
    _adjust_taxflow(
        total_output_tax_collected_delta      = +gst_amount,
        total_wht_withheld_by_customers_delta = +wht_amount,
        user=user,
    )


# ---------------------------------------------------------------------------
# TaxPayment services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_tax_payment(
    *, amount: Decimal, payment_date, method_allocations: list, note: str = "", user,
) -> TaxPayment:
    """
    Records a real GST payment made to FBR. Deducts amount from
    CashFlow.cash_in_hand (same mechanism as an Expense) and increases
    TaxFlow.total_sales_tax_paid, recalculating sales_tax_outstanding.
    """
    from rest_framework.exceptions import ValidationError

    if amount <= 0:
        raise ValidationError({"amount": "Payment amount must be greater than zero."})
    if not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected."})

    payment = TaxPayment.objects.create(
        amount=amount,
        payment_date=payment_date,
        note=note,
        created_by=user,
        updated_by=user,
    )

    _adjust_taxflow(total_sales_tax_paid_delta=+amount, user=user)

    from cash_flow.services import record_cash_movement, sync_tax_payment_made
    sync_tax_payment_made(amount=amount, user=user)
    record_cash_movement(payment)

    from payment_methods.services import record_allocations
    record_allocations(
        payment, direction="outflow", splits=method_allocations,
        total_amount=amount, date=payment_date, user=user,
    )

    return payment


@transaction.atomic
def delete_tax_payment(*, pk: int, user) -> None:
    """
    Soft-deletes a tax payment, restores its amount to cash_in_hand, and
    reverses it out of total_sales_tax_paid / sales_tax_outstanding.
    """
    from django.shortcuts import get_object_or_404

    payment = get_object_or_404(TaxPayment, pk=pk, is_deleted=False)
    amount  = payment.amount

    payment.is_deleted = True
    payment.deleted_at = timezone.now()
    payment.deleted_by = user
    payment.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    _adjust_taxflow(total_sales_tax_paid_delta=-amount, user=user)

    from cash_flow.services import reverse_cash_movement, sync_tax_payment_deleted
    sync_tax_payment_deleted(amount=amount, user=user)
    reverse_cash_movement(payment)

    from payment_methods.services import reverse_allocations
    reverse_allocations(payment)


# ---------------------------------------------------------------------------
# WHTPayment services
# ---------------------------------------------------------------------------

@transaction.atomic
def create_wht_payment(
    *, amount: Decimal, payment_date, method_allocations: list, note: str = "", user,
) -> WHTPayment:
    """
    Records a real WHT deposit made to FBR, against tax withheld from
    supplier payments. Deducts amount from CashFlow.cash_in_hand (same
    mechanism as a Tax Payment) and increases TaxFlow.total_wht_paid,
    recalculating wht_outstanding.
    """
    from rest_framework.exceptions import ValidationError

    if amount <= 0:
        raise ValidationError({"amount": "Payment amount must be greater than zero."})
    if not method_allocations:
        raise ValidationError({"method_allocations": "At least one method must be selected."})

    payment = WHTPayment.objects.create(
        amount=amount,
        payment_date=payment_date,
        note=note,
        created_by=user,
        updated_by=user,
    )

    _adjust_taxflow(total_wht_paid_delta=+amount, user=user)

    from cash_flow.services import record_cash_movement, sync_wht_payment_made
    sync_wht_payment_made(amount=amount, user=user)
    record_cash_movement(payment)

    from payment_methods.services import record_allocations
    record_allocations(
        payment, direction="outflow", splits=method_allocations,
        total_amount=amount, date=payment_date, user=user,
    )

    return payment


@transaction.atomic
def delete_wht_payment(*, pk: int, user) -> None:
    """
    Soft-deletes a WHT payment, restores its amount to cash_in_hand, and
    reverses it out of total_wht_paid / wht_outstanding.
    """
    from django.shortcuts import get_object_or_404

    payment = get_object_or_404(WHTPayment, pk=pk, is_deleted=False)
    amount  = payment.amount

    payment.is_deleted = True
    payment.deleted_at = timezone.now()
    payment.deleted_by = user
    payment.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    _adjust_taxflow(total_wht_paid_delta=-amount, user=user)

    from cash_flow.services import reverse_cash_movement, sync_wht_payment_deleted
    sync_wht_payment_deleted(amount=amount, user=user)
    reverse_cash_movement(payment)

    from payment_methods.services import reverse_allocations
    reverse_allocations(payment)
