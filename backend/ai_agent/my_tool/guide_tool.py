"""
get_guide(topic) — on-demand instructions (the "CLAUDE.md" idea): the base
prompt stays tiny and a topic's rules are only sent to the model when it asks
for them. Guide call/output are NOT stored in the chat session
(services.session.SKIPPED_TOOLS), so they never get re-sent on later turns.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from agents import function_tool
from django.conf import settings

GUIDES_DIR = Path(__file__).resolve().parent.parent / "instructions" / "guides"

Topic = Literal[
    "about", "sales", "receivables", "payables", "inventory",
    "cash", "profit", "tax", "assets", "formatting",
]
TOPICS = Topic.__args__


@lru_cache(maxsize=None)
def _read(topic: str) -> str:
    path = GUIDES_DIR / f"{topic}.md"
    if not path.is_file():
        return f"No guide written yet for '{topic}'."
    text = path.read_text(encoding="utf-8")
    return text.replace("{COMPANY_NAME}", getattr(settings, "COMPANY_NAME", "") or "the company")


@function_tool
def get_guide(topic: Topic) -> str:
    """Load the rules, definitions and facts for one topic before answering questions in that area.

    Args:
        topic: One of about, sales, receivables, payables, inventory, cash, profit, tax, assets, formatting.
    """
    return _read(topic)
