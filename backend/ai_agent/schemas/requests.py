"""Validated request bodies."""
from django.conf import settings
from pydantic import BaseModel, Field, field_validator


class ChatTitleIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title cannot be blank.")
        return v


class SendMessageIn(BaseModel):
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be blank.")
        if len(v) > settings.AGENT_MAX_INPUT_CHARS:
            raise ValueError(f"Message is too long (max {settings.AGENT_MAX_INPUT_CHARS} characters).")
        return v


class BulkBatchIn(BaseModel):
    """A list of invoice prompts (one invoice each) and an optional link-name filter."""
    prompts: list[str] = Field(min_length=1)
    link_name_id: int | None = None

    @field_validator("prompts")
    @classmethod
    def _clean(cls, values: list[str]) -> list[str]:
        if len(values) > settings.AGENT_BULK_MAX_ROWS:
            raise ValueError(f"At most {settings.AGENT_BULK_MAX_ROWS} invoices per batch.")
        cleaned = []
        for number, text in enumerate(values, start=1):
            text = (text or "").strip()
            if not text:
                raise ValueError(f"Invoice {number} is empty.")
            if len(text) > settings.AGENT_MAX_INPUT_CHARS:
                raise ValueError(f"Invoice {number} is too long (max {settings.AGENT_MAX_INPUT_CHARS} characters).")
            cleaned.append(text)
        return cleaned


class BulkAnswerIn(BaseModel):
    answer: str = Field(min_length=1)

    @field_validator("answer")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Answer cannot be blank.")
        if len(v) > 500:
            raise ValueError("Answer is too long (max 500 characters).")
        return v
