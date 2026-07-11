"""Find q_test_*.py files and collect the QuantumTests they define."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from qontinuum.runner.qtest import QuantumTest

TEST_FILE_GLOB = "q_test_*.py"
_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".qontinuum"}


@dataclass(frozen=True)
class DiscoveredTest:
    id: str  # "<relative file path>::<test name>"
    file: Path
    test: QuantumTest


class DiscoveryError(RuntimeError):
    """A test file could not be imported."""


def find_test_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files = [
        p
        for p in sorted(root.rglob(TEST_FILE_GLOB))
        if not _SKIP_DIRS.intersection(part for part in p.parts)
    ]
    return files


def discover(root: Path) -> list[DiscoveredTest]:
    """Import every test file under root and collect QuantumTest objects."""
    root = root.resolve()
    base = root if root.is_dir() else root.parent
    out: list[DiscoveredTest] = []
    for file in find_test_files(root):
        module = _import_file(file)
        rel = file.resolve().relative_to(base).as_posix()
        seen: set[int] = set()
        for obj in vars(module).values():
            if isinstance(obj, QuantumTest) and id(obj) not in seen:
                seen.add(id(obj))
                out.append(DiscoveredTest(id=f"{rel}::{obj.name}", file=file, test=obj))
    return out


def _import_file(file: Path):
    module_name = "qontinuum_tests." + "_".join(file.resolve().with_suffix("").parts[1:])
    spec = importlib.util.spec_from_file_location(module_name, file)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise DiscoveryError(f"cannot create import spec for {file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise DiscoveryError(f"failed to import {file}: {exc}") from exc
    return module
