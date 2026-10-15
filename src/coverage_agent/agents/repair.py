"""One retry after pytest fails."""

from pathlib import Path

from coverage_agent.llm import ChatHandle, invoke_structured
from coverage_agent.schemas import EditBatch, Plan

SYSTEM = """The last edit failed pytest. Return the full corrected file contents.
Keep every test that already passed. Do not add dependencies.
"""


def repair_edits(handle: ChatHandle, root: Path, plan: Plan, output: str) -> EditBatch:
    current = ""
    path = root / plan.file
    if path.is_file():
        current = path.read_text(encoding="utf-8")
    human = (
        f"Plan: {plan.instructions}\nFile: {plan.file}\n\n"
        f"pytest output:\n{output[-3000:]}\n\n"
        f"Current production file:\n{current}"
    )
    result = invoke_structured(handle, EditBatch, SYSTEM, human)
    return result if isinstance(result, EditBatch) else EditBatch.model_validate(result)
