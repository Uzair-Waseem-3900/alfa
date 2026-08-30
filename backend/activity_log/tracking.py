import logging

from django.apps import apps
from django.db.models.signals import post_delete, post_save

logger = logging.getLogger(__name__)

# The curated set of "headline" business models to track — deliberately NOT
# every model in the system. A business action that touches several child
# rows (e.g. confirming a purchase order with 50 line items, which loops
# and saves each PurchaseItem) must produce exactly ONE activity event, not
# 50 — so only the outer object each service function is really "about"
# gets a signal connected. Line items, shelf allocations, ledger entries,
# FIFO consumption rows, and singleton *Flow counters are intentionally
# absent — they're accounting detail of an already-tracked parent action,
# not their own reportable event.
TRACKED_MODELS = {
    ("purchases", "category"),
    ("purchases", "shelf"),
    ("purchases", "supplier"),
    ("purchases", "product"),
    ("purchases", "purchaseorder"),
    ("purchases", "supplierpayment"),
    ("purchases", "purchasereturn"),
    ("purchases", "lostinventoryrecord"),
    ("billing", "customer"),
    ("billing", "invoice"),
    ("billing", "payment"),
    ("billing", "return"),
    ("rates", "productrate"),
    ("cash_flow", "expensecategory"),
    ("cash_flow", "expense"),
    ("ledger", "savedledgerpdf"),
    ("ledger", "savedcustomerledgerpdf"),
    ("data_entry", "supplieropeningbalance"),
    ("data_entry", "customeropeningbalance"),
    ("data_entry", "openingcashentry"),
    ("taxes", "taxpayment"),
    ("taxes", "whtpayment"),
    ("cash_management", "cashadjustment"),
    ("cash_management", "investor"),
    ("cash_management", "investortransaction"),
    ("cash_management", "ownertransaction"),
    ("assets", "assetcategory"),
    ("assets", "asset"),
    ("recurring_expenses", "recurringexpensecategory"),
    ("recurring_expenses", "recurringexpense"),
    ("recurring_expenses", "recurringexpenseassignment"),
    ("recurring_expenses", "recurringexpenseassignmentpayment"),
    ("profits", "investorprofitpayout"),
    ("profits", "ownerprofitpayout"),
    ("backups", "backuphistory"),
    ("users", "user"),
}

# Tried in order against the instance; the first present+truthy value wins
# as the human-readable object label. Covers every tracked model's natural
# "reference" field without needing a per-model config entry — falls back
# to the model's own __str__ (every model in this codebase already
# implements one meaningfully).
_LABEL_FIELD_CANDIDATES = (
    "reference_number", "order_number", "bill_number", "name", "title", "email", "code",
)

# update_fields containing this name (with the field now True) is this
# codebase's universal soft-delete convention (AuditMixin._soft_delete) —
# detected generically instead of per-model.
_SOFT_DELETE_FIELD = "is_deleted"

# update_fields containing this name means a state-machine transition
# (confirm/accept/cancel/etc.) rather than a plain field edit — every
# tracked model that has a real status lifecycle (PurchaseOrder,
# PurchaseReturn, Invoice, Return) names it exactly this.
_STATUS_FIELD = "status"


def _object_repr(instance) -> str:
    for field in _LABEL_FIELD_CANDIDATES:
        value = getattr(instance, field, None)
        if value:
            return str(value)
    try:
        return str(instance)
    except Exception:
        return f"{instance.__class__.__name__} #{instance.pk}"


def _describe(sender, instance, *, created, deleted, update_fields):
    verbose_name = sender._meta.verbose_name
    label = _object_repr(instance)

    if created:
        return "create", f"Created {verbose_name} '{label}'"
    if deleted:
        return "delete", f"Deleted {verbose_name} '{label}'"
    if _SOFT_DELETE_FIELD in update_fields and getattr(instance, _SOFT_DELETE_FIELD, False):
        return "delete", f"Deleted {verbose_name} '{label}'"
    if _STATUS_FIELD in update_fields:
        get_display = getattr(instance, f"get_{_STATUS_FIELD}_display", None)
        status_value = get_display() if callable(get_display) else getattr(instance, _STATUS_FIELD, "")
        return "state_change", f"Changed {verbose_name} '{label}' status to {status_value}"
    if update_fields:
        return "update", f"Updated {verbose_name} '{label}' (fields: {', '.join(update_fields)})"
    return "update", f"Updated {verbose_name} '{label}'"


def _on_post_save(sender, instance, created, update_fields=None, **kwargs):
    try:
        from .services import record_activity
        fields = list(update_fields) if update_fields else []
        action, description = _describe(sender, instance, created=created, deleted=False, update_fields=fields)
        record_activity(
            action=action, instance=instance, description=description,
            object_repr=_object_repr(instance), changed_fields=fields,
        )
    except Exception:
        # An audit-log failure must never break the real business write it's
        # observing — log and move on.
        logger.exception("activity_log: failed to record post_save event for %s", sender)


def _on_post_delete(sender, instance, **kwargs):
    try:
        from .services import record_activity
        action, description = _describe(sender, instance, created=False, deleted=True, update_fields=[])
        record_activity(
            action=action, instance=instance, description=description,
            object_repr=_object_repr(instance), changed_fields=[],
        )
    except Exception:
        logger.exception("activity_log: failed to record post_delete event for %s", sender)


def connect_signals():
    """
    Called once from ActivityLogConfig.ready(). Resolves each (app_label,
    model_name) in TRACKED_MODELS to its model class and connects the two
    generic receivers with an explicit `sender` — cheaper than an
    unfiltered signal (Django skips the receiver call entirely for any
    non-matching sender) and means untracked models never touch this code
    at all, not even to be checked and skipped.
    """
    for app_label, model_name in TRACKED_MODELS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            logger.warning("activity_log: tracked model %s.%s not found, skipping", app_label, model_name)
            continue
        post_save.connect(_on_post_save, sender=model, weak=False, dispatch_uid=f"activity_log_save_{app_label}_{model_name}")
        post_delete.connect(_on_post_delete, sender=model, weak=False, dispatch_uid=f"activity_log_delete_{app_label}_{model_name}")
