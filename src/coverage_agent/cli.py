"""Command line. Stdout is one summary line. Failures go to stderr."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from coverage_agent.demo import FIXTURE, demo_handles
from coverage_agent.errors import CoverageError
from coverage_agent.gitwork import ensure_clean, start_branch
from coverage_agent.graph import build_graph, initial_state
from coverage_agent.llm import handles_for
from coverage_agent.measure import assert_python_project


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coverage-agent")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Raise pytest coverage in a repository")
    run.add_argument("path", nargs="?", help="Repository to edit")
    run.add_argument("--target", type=float, default=80)
    run.add_argument("--provider", default=None)
    run.add_argument("--max-rounds", type=int, default=5)
    run.add_argument(
        "--demo", action="store_true", help="Run the bundled fixture with a scripted model"
    )
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args)
    parser.error(f"Unknown command {args.command}")
    return 2


def _run(args: argparse.Namespace) -> int:
    if args.target <= 0 or args.target > 100:
        print("target must be between 0 and 100.", file=sys.stderr)
        return 1
    if args.max_rounds < 1:
        print("max-rounds must be at least 1.", file=sys.stderr)
        return 1
    workspace = None
    try:
        if args.demo:
            workspace = Path(tempfile.mkdtemp(prefix="coverage-agent-"))
            root = workspace / "fixture_app"
            shutil.copytree(FIXTURE, root)
            _demo_identity()
            _seed_git(root)
            handles = demo_handles()
        else:
            if not args.path:
                print("Pass a repository path, or use --demo.", file=sys.stderr)
                return 1
            root = Path(args.path).resolve()
            assert_python_project(root)
            ensure_clean(root)
            handles = handles_for(args.provider)
        branch = start_branch(root, args.target)
        graph = build_graph(handles, root)
        result = graph.invoke(
            initial_state(args.target, args.max_rounds, branch),
            config={"recursion_limit": 80},
        )
        summary = result.get("summary")
        if summary:
            print(summary, end="")
        else:
            percent = float(result.get("best_coverage", result.get("coverage", 0)))
            hit = "target hit" if percent >= args.target else "target not hit"
            print(f"{percent:.1f}% -> {percent:.1f}% on branch {branch} ({hit})")
        return 0
    except CoverageError as exc:
        print(f"{exc.kind}: {exc}", file=sys.stderr)
        return 1
    finally:
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)


def _demo_identity() -> None:
    os.environ["GIT_AUTHOR_NAME"] = "coverage-agent"
    os.environ["GIT_AUTHOR_EMAIL"] = "coverage-agent@example.com"
    os.environ["GIT_COMMITTER_NAME"] = "coverage-agent"
    os.environ["GIT_COMMITTER_EMAIL"] = "coverage-agent@example.com"


def _seed_git(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial fixture"], cwd=root, check=True, capture_output=True
    )


if __name__ == "__main__":
    raise SystemExit(main())
