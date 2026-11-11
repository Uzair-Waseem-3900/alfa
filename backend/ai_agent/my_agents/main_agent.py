from agents import Agent, ModelSettings

from ..config.configs import build_model
from ..instructions.base import build_instructions
from ..my_tool import ALL_TOOLS
from ..schemas.context import AgentContext


def build_agent() -> Agent[AgentContext]:
    """One agent, built per run (cheap; the model client must be per-loop).

    No `output_type`: the answer is free-form Markdown. No guardrails: the
    business-only rule lives in the prompt (decision: prompt is enough)."""
    return Agent[AgentContext](
        name="Business Assistant",
        instructions=build_instructions,
        model=build_model(),
        tools=ALL_TOOLS,
        model_settings=ModelSettings(temperature=0.2),  # factual answers, little randomness
    )
