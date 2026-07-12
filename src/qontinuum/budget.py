"""Hardware spend budgets and the run ledger — FinOps for QPU time.

Every `qont run` appends its estimated spend to ``.qontinuum/ledger.jsonl``.
Budgets configured via `qont budget set` are enforced *before* submission,
on top of the per-invocation ``--max-cost`` guard.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from qontinuum import config

LEDGER_FILE = "ledger.jsonl"


class BudgetExceededError(RuntimeError):
    """The configured budget would be exceeded; nothing was submitted."""


def ledger_path(root: Path) -> Path:
    base = root if root.is_dir() else root.parent
    return base / ".qontinuum" / LEDGER_FILE


def record_spend(root: Path, *, usd: float, target: str, tests: int) -> None:
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "usd": round(usd, 4),
        "target": target,
        "tests": tests,
    }
    with path.open("a") as fh:
        fh.write(json.dumps(entry, separators=(",", ":")) + "\n")


def read_ledger(root: Path) -> list[dict]:
    path = ledger_path(root)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def spent(root: Path, *, month: str | None = None) -> float:
    """Total estimated spend; restrict to a YYYY-MM month when given."""
    total = 0.0
    for entry in read_ledger(root):
        if month and not entry["at"].startswith(month):
            continue
        total += entry["usd"]
    return round(total, 4)


def check_budget(root: Path, upcoming_usd: float) -> None:
    """Raise BudgetExceededError if a run of ``upcoming_usd`` would bust a cap."""
    cfg = config.effective(root)
    monthly = cfg.get("budget.monthly_usd")
    total_cap = cfg.get("budget.total_usd")
    if monthly is not None:
        month = datetime.now(UTC).strftime("%Y-%m")
        month_spent = spent(root, month=month)
        if month_spent + upcoming_usd > monthly:
            raise BudgetExceededError(
                f"monthly budget ${monthly:,.2f}: already ${month_spent:,.2f} spent this "
                f"month, this run adds ${upcoming_usd:,.2f}. Raise it with "
                f"`qont budget set <usd> --monthly` or wait for next month."
            )
    if total_cap is not None:
        lifetime = spent(root)
        if lifetime + upcoming_usd > total_cap:
            raise BudgetExceededError(
                f"total budget ${total_cap:,.2f}: ${lifetime:,.2f} already spent, this run "
                f"adds ${upcoming_usd:,.2f}."
            )


def status(root: Path) -> dict:
    cfg = config.effective(root)
    month = datetime.now(UTC).strftime("%Y-%m")
    entries = read_ledger(root)
    return {
        "monthly_cap_usd": cfg.get("budget.monthly_usd"),
        "spent_this_month_usd": spent(root, month=month),
        "total_cap_usd": cfg.get("budget.total_usd"),
        "spent_total_usd": spent(root),
        "runs_recorded": len(entries),
        "last_run": entries[-1]["at"] if entries else None,
    }


def forecast(root: Path) -> dict | None:
    """Naive linear forecast of this month's spend from the run cadence."""
    month = datetime.now(UTC).strftime("%Y-%m")
    month_entries = [e for e in read_ledger(root) if e["at"].startswith(month)]
    if not month_entries:
        return None
    now = datetime.now(UTC)
    day = now.day
    month_spent = sum(e["usd"] for e in month_entries)
    daily_rate = month_spent / day
    days_in_month = 31 if now.month in {1, 3, 5, 7, 8, 10, 12} else (29 if now.month == 2 else 30)
    return {
        "month": month,
        "spent_so_far_usd": round(month_spent, 2),
        "daily_rate_usd": round(daily_rate, 2),
        "projected_month_usd": round(daily_rate * days_in_month, 2),
    }
