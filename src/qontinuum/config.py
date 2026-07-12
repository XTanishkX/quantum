"""Project configuration (.qontinuum/config.toml), git-config style.

Flat dotted keys grouped into TOML sections. Precedence everywhere in the CLI:
explicit flag > project config > built-in default. Unknown keys are rejected
with the list of valid ones — config typos should fail loudly, not silently.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

CONFIG_FILE = "config.toml"

#: key -> (default, description)
KNOWN_KEYS: dict[str, tuple[Any, str]] = {
    "defaults.seed": (None, "Simulator/transpiler seed applied when --seed is omitted"),
    "defaults.path": (".", "Default test-discovery path"),
    "defaults.snapshot_alpha": (0.01, "Two-sample alpha for snapshot comparison"),
    "budget.monthly_usd": (None, "Hardware spend cap per calendar month (qont run)"),
    "budget.total_usd": (None, "Lifetime hardware spend cap (qont run)"),
    "lint.ignore": ([], "Lint rule codes to skip, e.g. [\"Q003\"]"),
    "cache.enabled": (False, "Reuse cached results for unchanged seeded runs"),
    "report.junit_suite_name": ("qontinuum", "Suite name used in JUnit XML output"),
}


class ConfigError(ValueError):
    """Invalid key or unreadable config file."""


def config_path(root: Path) -> Path:
    return root / ".qontinuum" / CONFIG_FILE


def load(root: Path) -> dict[str, Any]:
    """Read the project config as flat dotted keys (defaults not filled in)."""
    path = config_path(root)
    if not path.is_file():
        return {}
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
    flat: dict[str, Any] = {}
    for section, values in raw.items():
        if isinstance(values, dict):
            for key, value in values.items():
                flat[f"{section}.{key}"] = value
        else:
            flat[section] = values
    for key in flat:
        _require_known(key)
    return flat


def effective(root: Path) -> dict[str, Any]:
    """Config with built-in defaults filled in for unset keys."""
    values = {key: default for key, (default, _) in KNOWN_KEYS.items()}
    values.update(load(root))
    return values


def get(root: Path, key: str) -> Any:
    _require_known(key)
    return load(root).get(key, KNOWN_KEYS[key][0])


def set_value(root: Path, key: str, raw_value: str) -> Any:
    _require_known(key)
    value = parse_value(raw_value)
    values = load(root)
    values[key] = value
    _write(root, values)
    return value


def unset(root: Path, key: str) -> bool:
    _require_known(key)
    values = load(root)
    existed = values.pop(key, None) is not None
    _write(root, values)
    return existed


def parse_value(raw: str) -> Any:
    """Interpret CLI-provided values: JSON when possible, else plain string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _require_known(key: str) -> None:
    if key not in KNOWN_KEYS:
        valid = ", ".join(sorted(KNOWN_KEYS))
        raise ConfigError(f"unknown config key {key!r}; valid keys: {valid}")


def _write(root: Path, values: dict[str, Any]) -> Path:
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    sections: dict[str, dict[str, Any]] = {}
    for key, value in sorted(values.items()):
        section, _, name = key.partition(".")
        sections.setdefault(section, {})[name] = value
    lines = ["# Qontinuum project configuration — managed by `qont config`.\n"]
    for section, entries in sections.items():
        lines.append(f"[{section}]")
        for name, value in entries.items():
            lines.append(f"{name} = {_toml_value(value)}")
        lines.append("")
    path.write_text("\n".join(lines))
    return path


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise ConfigError(f"cannot store value of type {type(value).__name__} in config")
