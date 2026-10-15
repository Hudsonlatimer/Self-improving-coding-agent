"""Branch, commit, and restore. The editor never gets a shell."""

import subprocess
from pathlib import Path

from coverage_agent.errors import CoverageError

_IGNORED = {".coverage", ".coverage-agent"}


def ensure_repo(root: Path) -> None:
    completed = _git(root, "rev-parse", "--is-inside-work-tree", check=False)
    if completed.returncode != 0 or completed.stdout.strip() != "true":
        raise CoverageError("not_git", f"{root} is not a git repository.")


def ensure_clean(root: Path) -> None:
    ensure_repo(root)
    dirty = dirty_entries(root)
    if dirty:
        preview = "\n".join(dirty[:8])
        raise CoverageError(
            "dirty_worktree",
            f"{root} has uncommitted changes. Commit or stash them before raising coverage.\n{preview}",
        )


def dirty_entries(root: Path) -> list[str]:
    completed = _git(root, "status", "--porcelain", check=False)
    if completed.returncode != 0:
        raise CoverageError("not_git", f"{root} is not a git repository.")
    rows: list[str] = []
    for line in completed.stdout.splitlines():
        path = line[3:].strip().replace("\\", "/")
        if path.startswith(".coverage-agent") or path in _IGNORED or path.endswith("/.coverage"):
            continue
        rows.append(line)
    return rows


def start_branch(root: Path, target: float) -> str:
    label = int(target) if float(target).is_integer() else str(target).replace(".", "-")
    base = f"coverage/raise-to-{label}"
    name = base
    suffix = 2
    while _exists(root, name):
        name = f"{base}-{suffix}"
        suffix += 1
    completed = _git(root, "checkout", "-b", name, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Could not create the branch.").strip()
        raise CoverageError("git", detail)
    return name


def commit_round(root: Path, message: str) -> bool:
    _git(root, "add", "-A", check=False)
    _git(root, "reset", "-q", "--", ".coverage", ".coverage-agent", check=False)
    staged = _git(root, "diff", "--cached", "--name-only", check=False)
    names = [line.strip() for line in staged.stdout.splitlines() if line.strip()]
    names = [name for name in names if not _ignored_name(name)]
    if not names:
        return False
    completed = _git(root, "commit", "-m", message, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "Commit failed.").strip()
        raise CoverageError("git", detail)
    return True


def restore(root: Path) -> None:
    _git(root, "reset", "--hard", "HEAD")
    _git(root, "clean", "-fd", "-e", ".coverage-agent")


def resolve_edit(root: Path, relative: str) -> Path:
    if not relative or relative.startswith(("/", "\\")):
        raise CoverageError("path_escape", f"Refusing path {relative!r}.")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise CoverageError("path_escape", f"Refusing path {relative!r}.")
    candidate = (root / path).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise CoverageError("path_escape", f"Refusing path {relative!r}.")
    if candidate.suffix != ".py":
        raise CoverageError("path_escape", f"Refusing non-Python path {relative!r}.")
    return candidate


def _exists(root: Path, name: str) -> bool:
    completed = _git(root, "rev-parse", "--verify", "--quiet", name, check=False)
    return completed.returncode == 0


def _ignored_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    return normalized == ".coverage" or normalized.startswith(".coverage-agent/")


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "git failed").strip()
        raise CoverageError("git", detail)
    return completed
