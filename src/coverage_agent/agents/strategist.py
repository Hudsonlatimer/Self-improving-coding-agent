"""Rewrite the checklist after a round that did not raise coverage."""

from coverage_agent.llm import ChatHandle, invoke_structured
from coverage_agent.schemas import StrategyUpdate

SYSTEM = """Rewrite the coverage checklist so the next round avoids the failure you just saw.
Keep it under 12 short lines. Do not include code.
"""


def rewrite_strategy(handle: ChatHandle, strategy: str, output: str, plan: dict) -> StrategyUpdate:
    human = (
        f"Current checklist:\n{strategy}\n\n"
        f"Plan that failed: {plan.get('file', '')} {plan.get('symbol', '')}\n"
        f"{plan.get('instructions', '')}\n\n"
        f"Output:\n{output[-2000:]}"
    )
    result = invoke_structured(handle, StrategyUpdate, SYSTEM, human)
    update = result if isinstance(result, StrategyUpdate) else StrategyUpdate.model_validate(result)
    if not update.checklist.strip():
        return StrategyUpdate(checklist=strategy)
    return update
