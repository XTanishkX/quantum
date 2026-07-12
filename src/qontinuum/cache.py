"""Content-addressed result cache — build caching for quantum simulation.

A seeded simulation is a pure function of ``(circuit hash, backend, shots,
seed)``, so its counts can be reused until any input changes — the same
insight that makes build caches work. Unseeded runs are never cached (their
randomness is the point).
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

CACHE_DIR = ".qontinuum/cache/results"


def cache_key(circuit_hash: str, backend: str, shots: int, seed: int) -> str:
    payload = f"{circuit_hash}|{backend}|{shots}|{seed}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _dir(root: Path) -> Path:
    base = root if root.is_dir() else root.parent
    return base / CACHE_DIR


def get(root: Path, key: str) -> dict[str, int] | None:
    path = _dir(root) / f"{key}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())["counts"]
    except (json.JSONDecodeError, KeyError):
        path.unlink(missing_ok=True)  # self-heal corrupt entries
        return None


def put(root: Path, key: str, counts: dict[str, int], *, meta: dict | None = None) -> None:
    directory = _dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{key}.json").write_text(
        json.dumps(
            {"counts": counts, "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
             **(meta or {})},
            separators=(",", ":"),
        )
    )


def entries(root: Path) -> list[dict]:
    directory = _dir(root)
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        out.append({
            "key": path.stem,
            "created_at": data.get("created_at"),
            "shots": sum(data.get("counts", {}).values()),
            "test": data.get("test"),
            "bytes": path.stat().st_size,
        })
    return out


def clear(root: Path) -> int:
    removed = 0
    for path in _dir(root).glob("*.json") if _dir(root).is_dir() else []:
        path.unlink()
        removed += 1
    return removed


def gc(root: Path, *, max_age_days: float = 30.0) -> int:
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for path in _dir(root).glob("*.json") if _dir(root).is_dir() else []:
        if path.stat().st_mtime < cutoff:
            path.unlink()
            removed += 1
    return removed
