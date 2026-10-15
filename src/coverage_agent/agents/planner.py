"""One uncovered region per round."""

from coverage_agent.llm import ChatHandle, invoke_structured
from coverage_agent.schemas import Plan

SYSTEM = """You pick one uncovered Python function to test next.
Choose the gap with the most missing lines.
Set edit_production only when the function hard-codes a value that a test cannot pass in.
instructions tell the editor exactly what to assert.
"""


def plan_gap(handle: ChatHandle, strategy: str, gaps: list[dict]) -> Plan:
    lines = []
    for gap in gaps[:8]:
        symbol = gap.get("symbol") or "(no symbol)"
        missing = ", ".join(str(number) for number in gap.get("missing_lines", [])[:12])
        lines.append(f"- {gap['path']} {symbol} missing lines {missing}")
        snippet = (gap.get("snippet") or "").strip()
        if snippet:
            lines.append(snippet)
            lines.append("")
    human = f"Checklist:\n{strategy}\n\nUncovered code:\n" + "\n".join(lines)
    result = invoke_structured(handle, Plan, SYSTEM, human)
    if not isinstance(result, Plan):
        return Plan.model_validate(result)
    return result
