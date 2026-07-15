"""The local telemetry outbox — an append-only queue under .qontinuum/telemetry.

Records are captured here first and only leave on an explicit ``qont telemetry
sync``. If there is no endpoint, no network, or the user never syncs, they simply
accumulate locally and can be inspected or cleared at any time — the offline path
is the default path. Each line is a signed, schema-versioned
:class:`TelemetryRecord`; corrupt or unverifiable lines are skipped on read.
"""

from __future__ import annotations

import json
from pathlib import Path

from qontinuum.telemetry.schema import TelemetryRecord

TELEMETRY_DIR = "telemetry"
OUTBOX_FILE = "outbox.jsonl"


def telemetry_dir(root: Path) -> Path:
    base = root if root.is_dir() else root.parent
    return base / ".qontinuum" / TELEMETRY_DIR


def outbox_path(root: Path) -> Path:
    return telemetry_dir(root) / OUTBOX_FILE


def append(root: Path, record: TelemetryRecord) -> Path:
    path = outbox_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(record.model_dump(), separators=(",", ":")) + "\n")
    return path


def read_all(root: Path) -> list[TelemetryRecord]:
    """Load queued records, skipping any that fail schema or integrity checks."""
    path = outbox_path(root)
    if not path.is_file():
        return []
    out: list[TelemetryRecord] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = TelemetryRecord.model_validate_json(line)
        except ValueError:
            continue  # corrupt line — never trust it
        if record.verify():
            out.append(record)
    return out


def count(root: Path) -> int:
    path = outbox_path(root)
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def clear(root: Path) -> int:
    """Remove the outbox; returns how many records were dropped."""
    n = count(root)
    path = outbox_path(root)
    if path.is_file():
        path.unlink()
    return n
