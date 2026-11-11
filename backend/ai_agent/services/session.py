"""
DjangoSession — the Django-backed equivalent of the SDK's SQLiteSession.

One session per chat. The SDK calls get_items() before a run (conversation
memory) and add_items() as the run produces items. The payload JSON is the
agent's memory; `kind` / `text` are derived here, once, for the visible
history.

Two cost controls live here:
  * get_items() returns only the last AGENT_HISTORY_ITEM_LIMIT items, cut at
    a USER-message boundary — cutting between a tool call and its output
    would send Gemini an orphaned tool result, which it rejects.
  * get_guide call/output items are never stored (they'd be re-sent on every
    later turn, defeating the point of loading guides on demand).
"""
from django.conf import settings
from django.utils import timezone
from agents.memory.session import SessionABC

from ..models import Chat, ChatItem

SKIPPED_TOOLS = frozenset({"get_guide"})


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") in ("input_text", "output_text", "text"):
                parts.append(part.get("text", ""))
        return "".join(parts)
    return ""


def classify(item: dict) -> tuple[str, str]:
    """-> (kind, visible text) for one SDK item."""
    role = item.get("role")
    if role == "user" and item.get("type", "message") == "message":
        return ChatItem.Kind.USER, _text_of(item.get("content"))
    if role == "assistant" and item.get("type", "message") == "message":
        return ChatItem.Kind.ASSISTANT, _text_of(item.get("content"))
    return ChatItem.Kind.OTHER, ""


def trim_to_user_boundary(items: list[dict]) -> list[dict]:
    """Drop leading items until the first user message."""
    for i, item in enumerate(items):
        if item.get("role") == "user":
            return items[i:]
    return []


class DjangoSession(SessionABC):
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.session_id = str(chat_id)
        self.session_settings = None
        self._skipped_call_ids: set[str] = set()

    async def get_items(self, limit: int | None = None) -> list[dict]:
        limit = limit or settings.AGENT_HISTORY_ITEM_LIMIT
        rows = [
            payload async for payload in
            ChatItem.objects.filter(chat_id=self.chat_id)
            .order_by("-id").values_list("payload", flat=True)[:limit]
        ]
        rows.reverse()
        return trim_to_user_boundary(rows)

    async def add_items(self, items: list[dict]) -> None:
        rows = []
        for item in items:
            if self._should_skip(item):
                continue
            kind, text = classify(item)
            rows.append(ChatItem(chat_id=self.chat_id, payload=item, kind=kind, text=text))
        if not rows:
            return
        await ChatItem.objects.abulk_create(rows)
        # QuerySet.update() bypasses auto_now, so bump the sort key explicitly.
        await Chat.all_objects.filter(pk=self.chat_id).aupdate(updated_at=timezone.now())

    async def pop_item(self) -> dict | None:
        last = await ChatItem.objects.filter(chat_id=self.chat_id).order_by("-id").afirst()
        if last is None:
            return None
        payload = last.payload
        await last.adelete()
        return payload

    async def clear_session(self) -> None:
        await ChatItem.objects.filter(chat_id=self.chat_id).adelete()

    def _should_skip(self, item: dict) -> bool:
        """Drop get_guide's function_call and its function_call_output."""
        if item.get("type") == "function_call" and item.get("name") in SKIPPED_TOOLS:
            self._skipped_call_ids.add(item.get("call_id", ""))
            return True
        if item.get("type") == "function_call_output" and item.get("call_id") in self._skipped_call_ids:
            return True
        return False
