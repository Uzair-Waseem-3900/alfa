from agents import Agent, ModelSettings

from ..config.configs import build_model
from ..instructions.bulk import build_instructions
from ..my_tool.bulk_tool import needs_attention, not_an_invoice
from ..my_tool.invoice_tool import create_draft_invoice, find_customer_for_invoice, find_product_for_invoice
from ..schemas.context import AgentContext

BULK_TOOLS = [find_customer_for_invoice, find_product_for_invoice, create_draft_invoice, needs_attention, not_an_invoice]


def build_bulk_agent() -> Agent[AgentContext]:
    """The invoice clerk: 5 tools (vs 20 for the chat assistant), no session/history, built per run."""
    return Agent[AgentContext](
        name="Invoice Clerk",
        instructions=build_instructions,
        model=build_model(),
        tools=BULK_TOOLS,
        model_settings=ModelSettings(temperature=0.2),
    )
