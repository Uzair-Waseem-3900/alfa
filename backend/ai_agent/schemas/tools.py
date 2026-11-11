"""
Types shared by tool signatures. Using Literals means the SDK puts an enum in
the tool's JSON schema, so the model cannot send a value we don't handle.
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, model_validator

PeriodName = Literal[
    "today", "yesterday", "last_7_days", "last_30_days",
    "this_week", "this_month", "last_month", "this_year", "last_year",
    "all_time", "custom",
]

InvoiceStatus = Literal["draft", "confirmed", "partial", "returned"]
PaymentStatus = Literal["unpaid", "partial", "paid"]


class PeriodRange(BaseModel):
    """A resolved reporting window. `date_from`/`date_to` are inclusive local
    (Asia/Karachi) calendar days; both None means all time."""
    label: str
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def _ordered(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self

    @property
    def is_all_time(self) -> bool:
        return self.date_from is None and self.date_to is None

    @property
    def from_str(self) -> str | None:
        return self.date_from.isoformat() if self.date_from else None

    @property
    def to_str(self) -> str | None:
        return self.date_to.isoformat() if self.date_to else None
