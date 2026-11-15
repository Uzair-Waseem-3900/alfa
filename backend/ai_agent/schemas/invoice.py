"""
What the model is allowed to send when it creates or edits an invoice draft.
Everything the model may NOT control (price, shelves, advance/payment, status)
is simply absent from these models, and unknown fields are refused.
"""
from typing import Literal

from django.conf import settings
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Optional numbers the model fills with 0 when it means "not given" (seen live: it sent
# discount_percent 0 AND discount_amount 0 AND gst 0 on every line, and quantity 0 on edits).
_ZERO_MEANS_UNSET = ("discount_percent", "discount_amount", "gst", "wht")

ResettableField = Literal["discount", "gst", "wht"]


class InvoiceLineIn(BaseModel):
    """One product line. On CREATE `quantity` is required; on UPDATE any field left out
    (or sent as null/0) keeps the line's current value. To REMOVE a discount/GST/WHT from
    an existing line say so explicitly with `reset`. Unknown fields (price, advance,
    status...) are REFUSED, not ignored."""
    model_config = ConfigDict(extra="forbid")

    product_id: int
    quantity: int | None = Field(default=None, ge=1)
    # Line discount, EITHER as a percent of the product's current rate OR as rupees off per unit.
    # NEGATIVE = SURCHARGE (price increase); billing stores it that way. The service keeps it within
    # +/- the product's rate. The sign is never changed: -2 means a Rs 2 surcharge per unit.
    discount_percent: float | None = Field(default=None, ge=-100, le=100, allow_inf_nan=False)
    discount_amount: float | None = Field(default=None, allow_inf_nan=False)
    gst: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)     # percent
    wht: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)     # percent
    reset: list[ResettableField] | None = None                                    # explicit "remove this" on an existing line

    @model_validator(mode="before")
    @classmethod
    def _zero_and_blank_mean_not_given(cls, data):
        if isinstance(data, dict):
            data = dict(data)
            for key in _ZERO_MEANS_UNSET:
                if key in data and data[key] in (0, 0.0, "", "0"):
                    data[key] = None
            if data.get("quantity") in (0, "", "0"):
                data["quantity"] = None
        return data

    @field_validator("reset")
    @classmethod
    def _dedupe_reset(cls, value):
        return sorted(set(value)) if value else None

    @model_validator(mode="after")
    def _one_discount_form(self):
        if self.discount_percent is not None and self.discount_amount is not None:
            raise ValueError("Give a line discount as a percent OR as an amount per unit, not both.")
        if self.quantity is not None and self.quantity > settings.AGENT_INVOICE_MAX_QTY:
            raise ValueError(f"Quantity is too large (max {settings.AGENT_INVOICE_MAX_QTY}).")
        return self


InvoiceDiscountType = Literal["percent", "flat"]
