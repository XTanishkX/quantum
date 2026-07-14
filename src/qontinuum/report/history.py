"""Append-only run history (.qontinuum/history.jsonl) — the local execution DB.

One JSON line per suite run: the local observability substrate that
``qont dashboard`` renders, ``qont history`` mines, and a future hosted platform
would ingest. Measurement counts are deliberately excluded (bulk); circuit
hashes, check statistics, and — since schema 2 — a structured ``execution``
record (provider, cost, runtime, outcome) are what trend analysis needs.

The record schema is **versioned and forward-compatible**: readers migrate older
lines up on read (:func:`migrate_record`), so a file written by any prior
version stays readable, and new optional fields never break old consumers. This
is what a later cloud sync ingests without a redesign.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from pydantic import BaseModel

from qontinuum.report.schema import SuiteResult

HISTORY_SCHEMA = 2
HISTORY_FILE = "history.jsonl"


class ExecutionRecord(BaseModel):
    """Structured metadata about *where and how* a suite ran (schema 2+).

    Every field beyond ``mode`` is optional and defaults to ``None`` — offline
    simulator runs fill almost none of it, a hardware run fills what it knows,
    and a future scheduler/cloud layer can populate the rest (actual cost, queue
    time) without a schema change.
    """

    mode: str  # "hardware" | "simulator"
    provider: str | None = None
    target: str | None = None
    backend: str | None = None
    estimated_cost_usd: float | None = None
    actual_cost_usd: float | None = None
    queue_time_s: float | None = None
    runtime_s: float | None = None
    routing_strategy: str | None = None
    calibration_age_days: int | None = None
    outcome: str | None = None  # suite status at execution time
    submitted_at: str | None = None
    completed_at: str | None = None


def history_path(root: Path) -> Path:
    base = root if root.is_dir() else root.parent
    return base / ".qontinuum" / HISTORY_FILE


def append_history(
    root: Path,
    suite: SuiteResult,
    *,
    cheapest_usd: float | None = None,
    execution: ExecutionRecord | dict | None = None,
) -> Path:
    if isinstance(execution, ExecutionRecord):
        execution = execution.model_dump()
    record = {
        "schema": HISTORY_SCHEMA,
        "created_at": suite.created_at.isoformat(timespec="seconds"),
        "tool_version": suite.tool_version,
        "seed": suite.seed,
        "git_sha": _git_sha(root),
        "status": suite.status.value,
        "tally": suite.tally(),
        "total_shots": sum(t.shots for t in suite.tests),
        "cheapest_usd": cheapest_usd,
        "execution": execution,
        "tests": [
            {
                "id": t.id,
                "status": t.status.value,
                "backend": t.backend,
                "shots": t.shots,
                "circuit_hash": t.circuit_hash,
                "duration_ms": t.duration_ms,
                "checks": [
                    {
                        "name": c.name,
                        "status": c.status.value,
                        "statistic": c.statistic,
                        "threshold": c.threshold,
                    }
                    for c in t.checks
                ],
            }
            for t in suite.tests
        ],
    }
    path = history_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    return path


def migrate_record(record: dict) -> dict:
    """Upgrade a history record to the current schema, in place-safe fashion.

    Old (schema 1) lines lack the ``execution`` field; we add it as ``None`` so
    every consumer sees one consistent shape. Migration only ever *adds*
    defaults — it never drops or reinterprets data — so it is safe to run on
    every read and to persist (``qont history prune`` rewrites migrated lines).
    """
    if record.get("schema", 1) >= HISTORY_SCHEMA and "execution" in record:
        return record
    upgraded = dict(record)
    upgraded["schema"] = HISTORY_SCHEMA
    upgraded.setdefault("execution", None)
    return upgraded


def read_history(root: Path) -> list[dict]:
    path = history_path(root)
    if not path.is_file():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            records.append(migrate_record(json.loads(line)))
    return records


def _git_sha(root: Path) -> str | None:
    env_sha = os.environ.get("GITHUB_SHA")
    if env_sha:
        return env_sha[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=root if root.is_dir() else root.parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return None
    sha = out.stdout.strip()
    return sha or None
