"""The receipt printed after a run. Each line names what that round did."""

from pathlib import Path

from coverage_agent.strategy import STRATEGY_DIR


def format_summary(
    start: float,
    end: float,
    branch: str,
    target: float,
    ledger: list[dict],
) -> str:
    hit = "target hit" if end >= target else "target not hit"
    lines = [f"{start:.1f}% -> {end:.1f}% on branch {branch} ({hit})"]
    for item in ledger:
        symbol = item.get("symbol") or item.get("file") or "coverage"
        file_name = item.get("file") or "coverage"
        if item.get("outcome") == "raised":
            delta = float(item["after"]) - float(item["before"])
            lines.append(f"round {item['round']}: covered {symbol} in {file_name} (+{delta:.1f})")
        else:
            lines.append(
                f"round {item['round']}: reverted {symbol} in {file_name} and rewrote the checklist"
            )
    return "\n".join(lines) + "\n"


def note_round(
    ledger: list[dict] | None,
    *,
    number: int,
    file_name: str,
    symbol: str,
    before: float,
    after: float,
    outcome: str,
) -> list[dict]:
    updated = list(ledger or [])
    updated.append(
        {
            "round": number,
            "file": file_name,
            "symbol": symbol,
            "before": before,
            "after": after,
            "outcome": outcome,
        }
    )
    return updated


def save_run_log(root: Path, text: str) -> Path:
    path = root / STRATEGY_DIR / "run.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return path
