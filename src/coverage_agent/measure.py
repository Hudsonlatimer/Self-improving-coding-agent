"""Run pytest under coverage.py and rank files by missing lines."""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from coverage_agent.errors import CoverageError
from coverage_agent.symbols import enclosing_symbol

_SKIP_PARTS = {".git", ".venv", "venv", ".coverage-agent", "__pycache__", "site-packages"}


@dataclass
class Gap:
    path: str
    missing_lines: list[int]
    symbol: str = ""
    snippet: str = ""

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "missing_lines": self.missing_lines,
            "symbol": self.symbol,
            "snippet": self.snippet,
        }


@dataclass
class Report:
    percent: float
    gaps: list[Gap] = field(default_factory=list)
    output: str = ""
    tests_passed: bool = False


def assert_python_project(root: Path) -> None:
    if not root.is_dir():
        raise CoverageError("not_python", f"{root} is not a directory.")
    py_files = [path for path in root.rglob("*.py") if not _skipped(path, root)]
    if not py_files:
        raise CoverageError(
            "not_python", f"{root} has no Python files. This agent only raises pytest coverage."
        )


def source_packages(root: Path) -> list[str]:
    names: list[str] = []
    for base in (root, root / "src"):
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / "__init__.py").is_file() and child.name not in {"tests"}:
                names.append(child.name)
    return names


def measure_project(root: Path) -> Report:
    passed, output = _run_pytest(root)
    payload = _coverage_json(root)
    percent = float((payload.get("totals") or {}).get("percent_covered") or 0)
    gaps = rank_gaps(payload, root)
    _attach_symbols(root, gaps)
    return Report(percent=percent, gaps=gaps, output=output, tests_passed=passed)


def rank_gaps(payload: dict, root: Path) -> list[Gap]:
    gaps: list[Gap] = []
    for raw_path, info in (payload.get("files") or {}).items():
        relative = _relative(root, raw_path)
        if relative is None or _skip_relative(relative):
            continue
        missing = [int(line) for line in info.get("missing_lines") or []]
        if not missing:
            continue
        gaps.append(Gap(path=relative, missing_lines=missing))
    gaps.sort(key=lambda gap: len(gap.missing_lines), reverse=True)
    return gaps


def _attach_symbols(root: Path, gaps: list[Gap]) -> None:
    for gap in gaps:
        file_path = root / gap.path
        if not file_path.is_file():
            continue
        source = file_path.read_text(encoding="utf-8")
        symbol = enclosing_symbol(source, gap.missing_lines[0])
        if symbol is None:
            continue
        gap.symbol = symbol.name
        gap.snippet = symbol.snippet


def _run_pytest(root: Path) -> tuple[bool, str]:
    command = [sys.executable, "-m", "coverage", "run", "-m", "pytest", "-q", "--tb=line"]
    packages = source_packages(root)
    if packages:
        command[4:4] = ["--source", ",".join(packages)]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CoverageError("pytest", "pytest timed out after 180 seconds.") from exc
    output = f"{completed.stdout or ''}{completed.stderr or ''}"
    return completed.returncode == 0, output[-4000:]


def _coverage_json(root: Path) -> dict:
    destination = root / ".coverage-agent" / "coverage.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [sys.executable, "-m", "coverage", "json", "-o", str(destination)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0 or not destination.is_file():
        return {"files": {}, "totals": {"percent_covered": 0}}
    return json.loads(destination.read_text(encoding="utf-8"))


def _relative(root: Path, raw_path: str) -> str | None:
    path = Path(raw_path)
    try:
        if path.is_absolute():
            return path.resolve().relative_to(root.resolve()).as_posix()
        return path.as_posix()
    except ValueError:
        return None


def _skip_relative(relative: str) -> bool:
    parts = Path(relative).parts
    name = parts[-1] if parts else relative
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return "tests" in parts or any(part in _SKIP_PARTS for part in parts)


def _skipped(path: Path, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return True
    return any(part in _SKIP_PARTS for part in relative.parts)
