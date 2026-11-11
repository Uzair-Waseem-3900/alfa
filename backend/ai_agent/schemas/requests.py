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
