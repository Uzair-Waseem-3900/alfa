"""
The two "stop" tools of the bulk-invoice agent. They only RECORD what the agent wants to report into the run
context; the row's status is decided in code afterwards (services.bulk_runner), never from the model's wording.
"""
from agents import RunContextWrapper

from ..schemas.context import AgentContext
from .base import agent_tool

MAX_QUESTION_CHARS = 400
MAX_OPTIONS = 8
MAX_OPTION_CHARS = 120


@agent_tool
def needs_attention(
    ctx: RunContextWrapper[AgentContext], question: str, options: list[str] | None = None,
) -> str:
    """Stop and ask the user ONE short question when you cannot create this invoice safely: a customer or product
    matches several records or none, a quantity is missing or unclear, stock is not enough, or the service refused.
    options = real choices only (the matching customers/products with code and address, or a concrete choice such as
    "Use 120 instead" / "Skip this product"); none when nothing was found. Create nothing after this.

    Args:
        question: One short question in the user's language.
        options: Up to 8 short answers the user may pick, e.g. "Uzair - ALFA-FSD-100 - Faisalabad".
    """
    ctx.context.outcome.question = (question or "").strip()[:MAX_QUESTION_CHARS] or "This request needs your attention."
    ctx.context.outcome.options = [str(o).strip()[:MAX_OPTION_CHARS] for o in (options or []) if str(o).strip()][:MAX_OPTIONS]
    return "Recorded. Stop now: do not create or change anything for this request."


@agent_tool
def not_an_invoice(ctx: RunContextWrapper[AgentContext], reason: str) -> str:
    """Call this when the message is not a request to create an invoice (a question, chat, a report request...).

    Args:
        reason: One short sentence saying what the message is.
    """
    ctx.context.outcome.not_invoice = (reason or "").strip()[:300] or "This is not an invoice request."
    return "Recorded. Stop now."
