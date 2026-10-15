"""Offline model used by --demo. It writes the one missing test and then stops."""

from pathlib import Path

from coverage_agent.llm import ChatHandle
from coverage_agent.schemas import EditBatch, FileEdit, Plan, StrategyUpdate

FIXTURE = Path(__file__).resolve().parents[2] / "examples" / "fixture_app"

TEST_FILE = """from fixture_app.calc import add, sub


def test_add():
    assert add(1, 2) == 3


def test_sub():
    assert sub(5, 2) == 3
"""


class DemoModel:
    def __init__(self, role: str) -> None:
        self.role = role

    def with_structured_output(self, schema):
        self._schema = schema
        return self

    def invoke(self, _messages):
        if self.role == "planner":
            return Plan(
                file="fixture_app/calc.py",
                symbol="sub",
                reason="sub has no test",
                edit_production=False,
                instructions="Add test_sub asserting sub(5, 2) == 3. Keep test_add.",
            )
        if self.role == "strategist":
            return StrategyUpdate(
                checklist="# Coverage checklist\n\n- Assert the return value of the uncovered function.\n"
            )
        return EditBatch(files=[FileEdit(path="tests/test_calc.py", content=TEST_FILE)])


def demo_handles() -> dict[str, ChatHandle]:
    return {
        role: ChatHandle(provider="demo", model="offline-demo", role=role, client=DemoModel(role))
        for role in ("planner", "editor", "repair", "strategist")
    }
