"""
What the model is allowed to send when it creates or edits an invoice draft.
Everything the model may NOT control (price, shelves, advance/payment, status)
is simply absent from these models.
"""
from typing import Literal

from django.conf import settings
from pydantic import BaseModel, ConfigDict, Field, model_validator


class InvoiceLineIn(BaseModel):
    """One product line. On CREATE `quantity` is required; on UPDATE any field
    left out keeps the line's current value. Unknown fields (price, advance, status...) are REFUSED, not ignored."""
    model_config = ConfigDict(extra="forbid")

    product_id: int
    quantity: int | None = Field(default=None, ge=1)
    # Line discount, EITHER as a percent of the product's current rate OR as rupees
    # off per unit. Positive only (the assistant never adds surcharges).
    discount_percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    discount_amount: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    gst: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)     # percent
    wht: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)     # percent

    @model_validator(mode="after")
    def _one_discount_form(self):
        if self.discount_percent is not None and self.discount_amount is not None:
            raise ValueError("Give a line discount as a percent OR as an amount per unit, not both.")
        if self.quantity is not None and self.quantity > settings.AGENT_INVOICE_MAX_QTY:
            raise ValueError(f"Quantity is too large (max {settings.AGENT_INVOICE_MAX_QTY}).")
        return self


InvoiceDiscountType = Literal["percent", "flat"]
