"""Consent and identity for the Quantum Intelligence Network.

Everything here defaults to **off**. Telemetry is opt-in via project config
(``telemetry.enabled``); until a user explicitly enables it, nothing is
captured, queued, or sent, and every other part of Qontinuum works exactly the
same. The anonymous ``install_id`` is a random uuid generated only at opt-in and
maps to no personal data.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from qontinuum import config


def is_enabled(root: Path) -> bool:
    """True only if the user explicitly opted in for this project."""
    try:
        return bool(config.get(root, "telemetry.enabled"))
    except config.ConfigError:  # pragma: no cover - defensive
        return False


def endpoint(root: Path) -> str:
    """Configured HTTPS endpoint, or "" to queue locally only."""
    return str(config.get(root, "telemetry.endpoint") or "")


def install_id(root: Path) -> str:
    return str(config.get(root, "telemetry.install_id") or "")


def enable(root: Path) -> str:
    """Opt in: set the flag and mint an anonymous install id if absent."""
    config.set_value(root, "telemetry.enabled", "true")
    existing = install_id(root)
    if not existing:
        existing = str(uuid.uuid4())
        config.set_value(root, "telemetry.install_id", existing)
    return existing


def disable(root: Path) -> None:
    """Opt out. The install id is left in place so re-opting-in is stable, but
    nothing is captured or sent while disabled."""
    config.set_value(root, "telemetry.enabled", "false")
