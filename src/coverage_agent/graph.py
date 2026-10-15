"""LangGraph loop. Stops at the target, after two flat rounds, or at max rounds."""

import sys
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from coverage_agent.agents.editor import apply_edits, propose_edits
from coverage_agent.agents.planner import plan_gap
from coverage_agent.agents.repair import repair_edits
from coverage_agent.agents.strategist import rewrite_strategy
from coverage_agent.errors import CoverageError
from coverage_agent.gitwork import commit_round, restore
from coverage_agent.llm import ChatHandle
from coverage_agent.measure import measure_project
from coverage_agent.schemas import Plan
from coverage_agent.strategy import load_strategy, save_strategy


class LoopState(TypedDict, total=False):
    target: float
    max_rounds: int
    round: int
    stalls: int
    coverage: float
    best_coverage: float
    gaps: list[dict[str, Any]]
    repaired: bool
    test_ok: bool
    coverage_delta: float
    hit: bool
    edit_error: str
    strategy: str
    plan: dict[str, Any]
    test_output: str


def route_after_measure(state: dict[str, Any]) -> Literal["plan", "finish"]:
    if state.get("coverage", 0) >= state["target"]:
        return "finish"
    if state.get("round", 0) >= state["max_rounds"]:
        return "finish"
    if state.get("stalls", 0) >= 2:
        return "finish"
    if not state.get("gaps"):
        return "finish"
    return "plan"


def route_after_test(state: dict[str, Any]) -> Literal["measure", "repair", "strategist"]:
    if state.get("test_ok") and state.get("coverage_delta", 0) > 0:
        return "measure"
    if not state.get("test_ok") and not state.get("repaired"):
        return "repair"
    return "strategist"


def route_after_strategist(state: dict[str, Any]) -> Literal["plan", "finish"]:
    if state.get("stalls", 0) >= 2 or state.get("round", 0) >= state["max_rounds"]:
        return "finish"
    return "plan"


def build_graph(handles: dict[str, ChatHandle], root: Path):
    def measure(state: dict[str, Any]) -> dict[str, Any]:
        _status(f"Measuring coverage (round {state.get('round', 0)})")
        report = measure_project(root)
        if state.get("round", 0) == 0 and not report.tests_passed:
            detail = report.output.strip() or "pytest failed before the agent made changes."
            raise CoverageError("pytest", detail)
        _status(f"Coverage {report.percent:.1f}%")
        return {
            "coverage": report.percent,
            "best_coverage": report.percent,
            "gaps": [gap.as_dict() for gap in report.gaps],
            "test_output": report.output,
            "test_ok": report.tests_passed,
        }

    def plan(state: dict[str, Any]) -> dict[str, Any]:
        strategy = load_strategy(root)
        chosen = plan_gap(handles["planner"], strategy, state.get("gaps") or [])
        _status(f"Planning {chosen.file} {chosen.symbol}".strip())
        return {
            "plan": chosen.model_dump(),
            "round": state.get("round", 0) + 1,
            "repaired": False,
            "strategy": strategy,
        }

    def edit(state: dict[str, Any]) -> dict[str, Any]:
        chosen = Plan.model_validate(state["plan"])
        batch = propose_edits(handles["editor"], root, chosen, state.get("strategy") or "")
        try:
            written = apply_edits(root, batch.files)
        except Exception as exc:
            return {"edit_error": str(exc), "test_ok": False}
        if not written:
            return {
                "edit_error": "The editor returned no files inside the repository.",
                "test_ok": False,
            }
        _status("Editing " + ", ".join(written))
        return {"edit_error": ""}

    def test(state: dict[str, Any]) -> dict[str, Any]:
        if state.get("edit_error"):
            return {"test_ok": False, "coverage_delta": 0.0, "test_output": state["edit_error"]}
        before = float(state.get("best_coverage", state.get("coverage", 0)))
        report = measure_project(root)
        delta = report.percent - before
        payload: dict[str, Any] = {
            "test_ok": report.tests_passed,
            "coverage": report.percent,
            "coverage_delta": delta,
            "test_output": report.output,
            "gaps": [gap.as_dict() for gap in report.gaps],
        }
        if report.tests_passed and delta > 0:
            file_name = (state.get("plan") or {}).get("file", "coverage")
            commit_round(root, f"Cover {file_name}")
            payload["best_coverage"] = report.percent
            _status(f"Tests passed. Coverage {report.percent:.1f}% (+{delta:.1f})")
        else:
            _status("Round did not raise coverage")
        return payload

    def repair(state: dict[str, Any]) -> dict[str, Any]:
        _status("Repairing the last edit")
        chosen = Plan.model_validate(state["plan"])
        batch = repair_edits(handles["repair"], root, chosen, state.get("test_output") or "")
        try:
            apply_edits(root, batch.files)
            return {"repaired": True, "edit_error": ""}
        except Exception as exc:
            return {"repaired": True, "edit_error": str(exc)}

    def strategist(state: dict[str, Any]) -> dict[str, Any]:
        _status("Updating the checklist")
        restore(root)
        update = rewrite_strategy(
            handles["strategist"],
            state.get("strategy") or load_strategy(root),
            state.get("test_output") or "",
            state.get("plan") or {},
        )
        save_strategy(root, update.checklist)
        return {"stalls": state.get("stalls", 0) + 1, "strategy": update.checklist}

    def finish(state: dict[str, Any]) -> dict[str, Any]:
        best = float(state.get("best_coverage", state.get("coverage", 0)))
        return {"hit": best >= state["target"], "best_coverage": best}

    graph = StateGraph(LoopState)
    graph.add_node("measure", measure)
    graph.add_node("plan", plan)
    graph.add_node("edit", edit)
    graph.add_node("test", test)
    graph.add_node("repair", repair)
    graph.add_node("strategist", strategist)
    graph.add_node("finish", finish)
    graph.add_edge(START, "measure")
    graph.add_conditional_edges(
        "measure", route_after_measure, {"plan": "plan", "finish": "finish"}
    )
    graph.add_edge("plan", "edit")
    graph.add_edge("edit", "test")
    graph.add_conditional_edges(
        "test",
        route_after_test,
        {"measure": "measure", "repair": "repair", "strategist": "strategist"},
    )
    graph.add_edge("repair", "test")
    graph.add_conditional_edges(
        "strategist", route_after_strategist, {"plan": "plan", "finish": "finish"}
    )
    graph.add_edge("finish", END)
    return graph.compile()


def initial_state(target: float, max_rounds: int) -> dict[str, Any]:
    return {
        "target": target,
        "max_rounds": max_rounds,
        "round": 0,
        "stalls": 0,
        "coverage": 0.0,
        "best_coverage": 0.0,
        "gaps": [],
        "repaired": False,
        "test_ok": False,
        "coverage_delta": 0.0,
        "hit": False,
        "edit_error": "",
        "strategy": "",
        "plan": {},
        "test_output": "",
    }


def _status(message: str) -> None:
    print(message, file=sys.stderr)
