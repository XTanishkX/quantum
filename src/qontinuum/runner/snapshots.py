"""Golden-baseline snapshot store (.qontinuum/snapshots.json, committed to the repo).

Semantics mirror Jest snapshots: when the circuit's content hash changes the
snapshot is *stale* — the developer reviews the new behavior and runs
``qont snapshot update``. When the hash is unchanged, the new sample is
compared against the baseline sample with a two-sample homogeneity test,
catching drift from dependency upgrades, transpiler changes, or noise models.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

SNAPSHOT_SCHEMA = 1
SNAPSHOT_DIR = ".qontinuum"
SNAPSHOT_FILE = "snapshots.json"


class SnapshotStore:
    def __init__(self, root: Path):
        self.path = root / SNAPSHOT_DIR / SNAPSHOT_FILE
        self._data: dict = {"schema": SNAPSHOT_SCHEMA, "snapshots": {}}
        if self.path.is_file():
            self._data = json.loads(self.path.read_text())

    def get(self, test_id: str) -> dict | None:
        return self._data["snapshots"].get(test_id)

    def put(
        self, test_id: str, *, circuit_hash: str, backend: str, shots: int,
        counts: dict[str, int],
    ) -> None:
        self._data["snapshots"][test_id] = {
            "circuit_hash": circuit_hash,
            "backend": backend,
            "shots": shots,
            "counts": counts,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True) + "\n")
