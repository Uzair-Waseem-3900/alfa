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

# One-line meaning of topics whose name alone doesn't say what questions they
# answer. Used in the base prompt so the model knows WHEN to open a guide
# (without this, "who built you?" was answered with "no tool can answer").
TOPIC_HINTS = {
    "about": "you, the company, the developer",
}


def topics_text() -> str:
    return ", ".join(f"{t} ({TOPIC_HINTS[t]})" if t in TOPIC_HINTS else t for t in TOPICS)


@lru_cache(maxsize=None)
def _read(topic: str) -> str:
    path = GUIDES_DIR / f"{topic}.md"
    if not path.is_file():
        return f"No guide written yet for '{topic}'."
    text = path.read_text(encoding="utf-8")
    return text.replace("{COMPANY_NAME}", getattr(settings, "COMPANY_NAME", "") or "the company")


@function_tool
def get_guide(topic: Topic) -> str:
    """Load the facts and rules for one topic. Use topic "about" for any question about the assistant itself,
    the company (ALFA Industries, its owners) or the developer who built it. Use the others for definitions
    and rules in that business area before answering.

    Args:
        topic: One of about, sales, receivables, payables, inventory, cash, profit, tax, assets, formatting.
    """
    return _read(topic)
