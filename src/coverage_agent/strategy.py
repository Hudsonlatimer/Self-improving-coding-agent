"""Checklist the planner reads. A failed round rewrites the copy in the target repo."""

from pathlib import Path

STRATEGY_DIR = ".coverage-agent"
STRATEGY_NAME = "strategy.md"

_FALLBACK = """# Coverage checklist

- Read the uncovered function before writing a test.
- Assert the return value or the raised error.
- Keep every existing test.
- Change production code only to pass in a hard-coded value, with the old value as the default.
- Touch at most one production file and one test file in a round.
- Do not add dependencies.
"""


def strategy_path(root: Path) -> Path:
    return root / STRATEGY_DIR / STRATEGY_NAME


def default_strategy() -> str:
    bundled = Path(__file__).resolve().parent / "prompts" / "default_strategy.md"
    if bundled.is_file():
        return bundled.read_text(encoding="utf-8")
    return _FALLBACK


def load_strategy(root: Path) -> str:
    path = strategy_path(root)
    if path.is_file():
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text + "\n"
    return default_strategy()


def save_strategy(root: Path, checklist: str) -> Path:
    path = strategy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = checklist.strip() + "\n"
    path.write_text(text, encoding="utf-8")
    return path
