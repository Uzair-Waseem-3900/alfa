"""
SSE event payloads (what the browser receives). Pydantic so the wire format
is defined — and restricted — in exactly one place.

  step       a tool started          {"call_id", "name", "label"}
  step_done  a tool finished         {"call_id", "name"}
  token      a chunk of answer text  {"text"}
  done       run finished            {"text"}   (full final answer)
  error      run failed              {"message"}
  reset      discard the answer so far, a retry is starting   {"reason"}
"""
from typing import Literal

from pydantic import BaseModel


class StepEvent(BaseModel):
    call_id: str
    name: str
    label: str


class StepDoneEvent(BaseModel):
    call_id: str
    name: str


class TokenEvent(BaseModel):
    text: str


class DoneEvent(BaseModel):
    text: str


class ErrorEvent(BaseModel):
    message: str


class ResetEvent(BaseModel):
    reason: str


EventType = Literal["step", "step_done", "token", "done", "error", "reset"]

_EVENT_TYPES = {
    "step": StepEvent,
    "step_done": StepDoneEvent,
    "token": TokenEvent,
    "done": DoneEvent,
    "error": ErrorEvent,
    "reset": ResetEvent,
}

TERMINAL_EVENTS = frozenset({"done", "error"})


def dump_event(event_type: EventType, **data) -> str:
    """Validate against the event's model and return its JSON string."""
    return _EVENT_TYPES[event_type](**data).model_dump_json()
