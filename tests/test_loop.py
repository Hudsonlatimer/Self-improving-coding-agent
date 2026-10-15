import os
import subprocess
from pathlib import Path

import pytest

from coverage_agent.agents.editor import select_edits
from coverage_agent.cli import main
from coverage_agent.errors import CoverageError
from coverage_agent.gitwork import commit_round, dirty_entries, ensure_clean, resolve_edit, restore
from coverage_agent.graph import route_after_measure, route_after_strategist, route_after_test
from coverage_agent.measure import rank_gaps
from coverage_agent.schemas import FileEdit, Plan
from coverage_agent.strategy import load_strategy, save_strategy
from coverage_agent.symbols import enclosing_symbol


def test_rank_gaps_orders_the_largest_hole_first(tmp_path: Path):
    payload = {
        "files": {
            "pkg/a.py": {"missing_lines": [1]},
            "pkg/b.py": {"missing_lines": [4, 5, 6]},
            "tests/test_a.py": {"missing_lines": [1, 2, 3, 4]},
        },
        "totals": {"percent_covered": 40},
    }
    gaps = rank_gaps(payload, tmp_path)
    assert [gap.path for gap in gaps] == ["pkg/b.py", "pkg/a.py"]


def test_symbol_names_the_uncovered_function():
    source = "def add(left, right):\n    return left + right\n\ndef sub(left, right):\n    return left - right\n"
    symbol = enclosing_symbol(source, 4)
    assert symbol is not None
    assert symbol.name == "sub"


def test_path_escape_is_rejected(tmp_path: Path):
    with pytest.raises(CoverageError) as exc:
        resolve_edit(tmp_path, "../outside.py")
    assert exc.value.kind == "path_escape"
    with pytest.raises(CoverageError):
        resolve_edit(tmp_path, "notes.md")


def test_editor_keeps_tests_when_production_edits_are_off():
    plan = Plan(file="pkg/a.py", reason="gap", edit_production=False, instructions="test it")
    files = [
        FileEdit(path="pkg/a.py", content="x = 1\n"),
        FileEdit(path="tests/test_a.py", content="def test_a():\n    assert True\n"),
    ]
    chosen = select_edits(plan, files)
    assert [edit.path for edit in chosen] == ["tests/test_a.py"]


def test_strategy_roundtrip_uses_the_saved_checklist(tmp_path: Path):
    assert "uncovered function" in load_strategy(tmp_path)
    save_strategy(tmp_path, "# Coverage checklist\n\n- Assert the return value.\n")
    assert "Assert the return value" in load_strategy(tmp_path)


def test_routes_stop_at_the_target_and_after_two_stalls():
    assert (
        route_after_measure(
            {"coverage": 80, "target": 80, "round": 1, "max_rounds": 5, "stalls": 0, "gaps": [{}]}
        )
        == "finish"
    )
    assert (
        route_after_measure(
            {"coverage": 10, "target": 80, "round": 5, "max_rounds": 5, "stalls": 0, "gaps": [{}]}
        )
        == "finish"
    )
    assert (
        route_after_measure(
            {"coverage": 10, "target": 80, "round": 1, "max_rounds": 5, "stalls": 2, "gaps": [{}]}
        )
        == "finish"
    )
    assert (
        route_after_measure(
            {"coverage": 10, "target": 80, "round": 1, "max_rounds": 5, "stalls": 0, "gaps": [{}]}
        )
        == "plan"
    )
    assert route_after_test({"test_ok": True, "coverage_delta": 5, "repaired": False}) == "measure"
    assert route_after_test({"test_ok": False, "coverage_delta": 0, "repaired": False}) == "repair"
    assert (
        route_after_test({"test_ok": False, "coverage_delta": 0, "repaired": True}) == "strategist"
    )
    assert (
        route_after_test({"test_ok": True, "coverage_delta": 0, "repaired": False}) == "strategist"
    )
    assert route_after_strategist({"stalls": 2, "round": 1, "max_rounds": 5}) == "finish"
    assert route_after_strategist({"stalls": 1, "round": 1, "max_rounds": 5}) == "plan"


def test_git_refuses_a_dirty_tree_and_can_commit_then_restore(tmp_path: Path):
    _git_identity()
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "keep.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "start"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "new.py").write_text("y = 2\n", encoding="utf-8")
    with pytest.raises(CoverageError) as exc:
        ensure_clean(tmp_path)
    assert exc.value.kind == "dirty_worktree"
    assert commit_round(tmp_path, "Cover keep.py")
    assert not dirty_entries(tmp_path)
    (tmp_path / "discard.py").write_text("z = 3\n", encoding="utf-8")
    restore(tmp_path)
    assert not (tmp_path / "discard.py").exists()
    assert (tmp_path / "new.py").is_file()


def test_demo_reaches_full_coverage(capsys: pytest.CaptureFixture[str]):
    code = main(["run", "--demo", "--target", "100", "--max-rounds", "2"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert "coverage 100.0% on branch coverage/raise-to-100 (target hit)" in captured.out


def test_non_python_and_missing_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["run", str(empty)]) == 1
    assert "not_python" in capsys.readouterr().err

    project = tmp_path / "py"
    project.mkdir()
    (project / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _git_identity()
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "add", "mod.py"], cwd=project, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "start"], cwd=project, check=True, capture_output=True)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    assert main(["run", str(project), "--provider", "groq"]) == 1
    assert "missing_key" in capsys.readouterr().err


@pytest.mark.live
def test_live_planner_answers():
    from coverage_agent.agents.planner import plan_gap
    from coverage_agent.llm import get_chat_model

    handle = get_chat_model("groq", role="planner")
    plan = plan_gap(
        handle,
        "Assert the return value.",
        [
            {
                "path": "pkg/calc.py",
                "symbol": "sub",
                "missing_lines": [4],
                "snippet": "def sub(a, b):\n    return a - b",
            }
        ],
    )
    assert plan.file


def _git_identity() -> None:
    os.environ["GIT_AUTHOR_NAME"] = "coverage-agent"
    os.environ["GIT_AUTHOR_EMAIL"] = "coverage-agent@example.com"
    os.environ["GIT_COMMITTER_NAME"] = "coverage-agent"
    os.environ["GIT_COMMITTER_EMAIL"] = "coverage-agent@example.com"
