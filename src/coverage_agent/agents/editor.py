"""Write full Python files. Paths are checked before anything is saved."""

from pathlib import Path

from coverage_agent.gitwork import resolve_edit
from coverage_agent.llm import ChatHandle, invoke_structured
from coverage_agent.schemas import EditBatch, FileEdit, Plan

SYSTEM = """You write the complete contents of each file you change.
Return at most two files: one test file and, only if the plan says so, one production file.
Keep every existing test. Do not add dependencies. Do not invent files outside the repository.
"""


def propose_edits(handle: ChatHandle, root: Path, plan: Plan, strategy: str) -> EditBatch:
    current = _read(root, plan.file)
    human = (
        f"Checklist:\n{strategy}\n\n"
        f"Plan: {plan.instructions}\n"
        f"File: {plan.file}\nSymbol: {plan.symbol}\n"
        f"Edit production: {plan.edit_production}\n\n"
        f"Current file:\n{current}"
    )
    result = invoke_structured(handle, EditBatch, SYSTEM, human)
    batch = result if isinstance(result, EditBatch) else EditBatch.model_validate(result)
    return EditBatch(files=select_edits(plan, batch.files))


def select_edits(plan: Plan, files: list[FileEdit]) -> list[FileEdit]:
    chosen: list[FileEdit] = []
    for edit in files:
        if len(chosen) >= 3:
            break
        if not plan.edit_production and not _is_test(edit.path):
            continue
        chosen.append(edit)
    return chosen


def apply_edits(root: Path, files: list[FileEdit]) -> list[str]:
    written: list[str] = []
    for edit in files[:3]:
        path = resolve_edit(root, edit.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(edit.content, encoding="utf-8")
        written.append(edit.path.replace("\\", "/"))
    return written


def _is_test(relative: str) -> bool:
    parts = Path(relative).parts
    name = parts[-1] if parts else relative
    return "tests" in parts or name.startswith("test_") or name.endswith("_test.py")


def _read(root: Path, relative: str) -> str:
    path = root / relative
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")
