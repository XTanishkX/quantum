"""Reproducibility bundles: package a suite, its baselines, results, and the
environment that produced them into one verifiable artifact.

``verify`` re-runs the packed suite in the *current* environment and compares
each test's distribution against the packed one with a two-sample test —
"does this result reproduce here?" answered mechanically.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

PACK_SCHEMA = 1
MANIFEST = "qontinuum-pack.json"


class PackError(RuntimeError):
    pass


def create_pack(root: Path, out: Path, *, seed: int = 42) -> dict:
    """Run the suite seeded, then bundle tests + snapshots + results + env."""
    from qontinuum.cli_groups.scaffold_cmds import _environment
    from qontinuum.cost import load_catalog
    from qontinuum.runner.discovery import find_test_files
    from qontinuum.runner.engine import run_suite

    files = find_test_files(root)
    if not files:
        raise PackError(f"no q_test_*.py files under {root}")
    suite = run_suite(root, seed=seed)

    base = root if root.is_dir() else root.parent
    manifest = {
        "schema": PACK_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": seed,
        "environment": _environment(),
        "catalog_verified": load_catalog()["verified"],
        "suite": json.loads(suite.model_dump_json()),
        "files": {},
    }

    with tarfile.open(out, "w:gz") as tar:
        for file in files:
            rel = file.resolve().relative_to(base.resolve()).as_posix()
            data = file.read_bytes()
            manifest["files"][rel] = hashlib.sha256(data).hexdigest()
            _add_bytes(tar, f"suite/{rel}", data)
        snapshots = base / ".qontinuum" / "snapshots.json"
        if snapshots.is_file():
            data = snapshots.read_bytes()
            manifest["files"][".qontinuum/snapshots.json"] = hashlib.sha256(data).hexdigest()
            _add_bytes(tar, "suite/.qontinuum/snapshots.json", data)
        _add_bytes(tar, MANIFEST, json.dumps(manifest, indent=2).encode())
    return manifest


def inspect_pack(bundle: Path) -> dict:
    with tarfile.open(bundle, "r:gz") as tar:
        member = tar.extractfile(MANIFEST)
        if member is None:
            raise PackError(f"{bundle} has no {MANIFEST} — not a qontinuum pack")
        return json.loads(member.read())


def verify_pack(bundle: Path, *, alpha: float = 0.01) -> list[dict]:
    """Re-run the packed suite here; two-sample compare against packed counts."""
    from qontinuum.assertions.stats import two_sample_pvalue
    from qontinuum.runner.engine import run_suite

    manifest = inspect_pack(bundle)
    with tempfile.TemporaryDirectory(prefix="qontinuum-pack-") as tmp:
        workdir = Path(tmp)
        with tarfile.open(bundle, "r:gz") as tar:
            tar.extractall(workdir, filter="data")
        suite_dir = workdir / "suite"
        rerun = run_suite(suite_dir, seed=manifest["seed"])

    packed_tests = {t["id"]: t for t in manifest["suite"]["tests"]}
    results: list[dict] = []
    for test in rerun.tests:
        packed = packed_tests.get(test.id)
        if packed is None:
            results.append({"test": test.id, "verdict": "new (not in pack)"})
            continue
        if packed["circuit_hash"] != test.circuit_hash:
            results.append({"test": test.id, "verdict": "CIRCUIT CHANGED", "p_value": None})
            continue
        if not packed.get("counts") or not test.counts:
            results.append({"test": test.id, "verdict": "no counts to compare"})
            continue
        _, p_value = two_sample_pvalue(test.counts, packed["counts"])
        reproduces = p_value >= alpha
        results.append({
            "test": test.id,
            "p_value": round(p_value, 6),
            "verdict": "reproduces" if reproduces else "DOES NOT REPRODUCE",
        })
    missing = set(packed_tests) - {t.id for t in rerun.tests}
    results.extend({"test": t, "verdict": "MISSING in rerun"} for t in sorted(missing))
    return results


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0  # deterministic archives
    tar.addfile(info, io.BytesIO(data))
