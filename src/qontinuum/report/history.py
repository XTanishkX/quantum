"""Append-only run history (.qontinuum/history.jsonl).

One JSON line per suite run — the local observability substrate that
``qont dashboard`` renders and a future hosted dashboard would ingest.
Measurement counts are deliberately excluded (bulk); circuit hashes and check
statistics are what trend analysis needs.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from qontinuum.report.schema import SuiteResult

HISTORY_SCHEMA = 1
HISTORY_FILE = "history.jsonl"


def history_path(root: Path) -> Path:
    base = root if root.is_dir() else root.parent
    return base / ".qontinuum" / HISTORY_FILE


def append_history(
    root: Path, suite: SuiteResult, *, cheapest_usd: float | None = None
) -> Path:
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


def read_history(root: Path) -> list[dict]:
    path = history_path(root)
    if not path.is_file():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
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
