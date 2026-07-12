"""Named circuit registry with hash lineage — git for experiment circuits.

``.qontinuum/registry.json`` maps human names to a version history of
canonical content hashes, so "the ansatz" has an auditable evolution
independent of file paths and refactors.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

REGISTRY_SCHEMA = 1
REGISTRY_FILE = "registry.json"


class RegistryError(ValueError):
    pass


class CircuitRegistry:
    def __init__(self, root: Path):
        base = root if root.is_dir() else root.parent
        self.path = base / ".qontinuum" / REGISTRY_FILE
        self._data: dict = {"schema": REGISTRY_SCHEMA, "circuits": {}}
        if self.path.is_file():
            self._data = json.loads(self.path.read_text())

    def add(self, name: str, *, circuit_hash: str, source: str, note: str = "") -> dict:
        entry = self._data["circuits"].setdefault(name, {"versions": []})
        versions = entry["versions"]
        if versions and versions[-1]["hash"] == circuit_hash:
            raise RegistryError(
                f"{name!r} is already at this hash (v{len(versions)}); nothing to add"
            )
        version = {
            "version": len(versions) + 1,
            "hash": circuit_hash,
            "source": source,
            "note": note,
            "tags": [],
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        versions.append(version)
        self._save()
        return version

    def names(self) -> list[dict]:
        out = []
        for name, entry in sorted(self._data["circuits"].items()):
            latest = entry["versions"][-1]
            out.append({
                "name": name,
                "versions": len(entry["versions"]),
                "latest_hash": latest["hash"],
                "tags": latest["tags"],
                "updated_at": latest["created_at"],
            })
        return out

    def get(self, name: str) -> dict:
        entry = self._data["circuits"].get(name)
        if entry is None:
            raise RegistryError(f"no registered circuit named {name!r}")
        return entry

    def log(self, name: str) -> list[dict]:
        return list(reversed(self.get(name)["versions"]))

    def tag(self, name: str, tag: str, *, version: int | None = None) -> dict:
        versions = self.get(name)["versions"]
        target = versions[(version - 1) if version else -1]
        if tag not in target["tags"]:
            target["tags"].append(tag)
            self._save()
        return target

    def remove(self, name: str) -> None:
        self.get(name)
        del self._data["circuits"][name]
        self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True) + "\n")
