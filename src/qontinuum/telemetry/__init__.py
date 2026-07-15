"""The Quantum Intelligence Network client — opt-in, anonymous, offline-first.

Qontinuum can optionally contribute *anonymous hardware-execution metadata* to a
community intelligence network that improves recommendations for everyone. The
guarantees, enforced by this package:

- **Off by default.** Nothing is captured, queued, or sent until the user runs
  ``qont telemetry enable``. Every feature works identically with it off.
- **Anonymous & minimal.** Only an allowlist of engineering metadata leaves the
  machine (see :class:`~qontinuum.telemetry.schema.TelemetryRecord`). Circuits,
  distributions, snapshots, counts, source, credentials, and identity are never
  collected — there is no field for them.
- **Offline-first.** Records queue locally and only leave on an explicit
  ``qont telemetry sync``; any network failure leaves the queue intact.

Public API::

    from qontinuum import telemetry
    telemetry.capture(root, history_record)   # no-op unless opted in
    telemetry.sync(root)
"""

from __future__ import annotations

from pathlib import Path

from qontinuum.telemetry import consent, outbox, scrub
from qontinuum.telemetry.client import SyncResult, pull_community, sync
from qontinuum.telemetry.community import load as load_community
from qontinuum.telemetry.schema import (
    CommunityAggregate,
    CommunityDeviceStat,
    TelemetryRecord,
)

__all__ = [
    "CommunityAggregate",
    "CommunityDeviceStat",
    "SyncResult",
    "TelemetryRecord",
    "capture",
    "consent",
    "load_community",
    "outbox",
    "preview",
    "pull_community",
    "scrub",
    "sync",
]


def capture(root: Path, history_record: dict, *, tool_version: str | None = None) -> bool:
    """Queue one anonymous record from a just-written history record.

    A no-op (returns ``False``) unless telemetry is enabled and the record is a
    hardware execution. Never raises — telemetry must not affect a run's outcome.
    """
    try:
        if not consent.is_enabled(root):
            return False
        record = scrub.build_record(
            history_record, install_id=consent.install_id(root), tool_version=tool_version
        )
        if record is None:
            return False
        outbox.append(root, record)
        return True
    except Exception:  # telemetry failures must be invisible to the workflow
        return False


def preview(root: Path, history_records: list[dict]) -> list[TelemetryRecord]:
    """Exactly what *would* be contributed from these history records.

    The transparency primitive behind ``qont telemetry preview`` — build the
    anonymous records without queuing or sending anything.
    """
    install = consent.install_id(root) or "<anonymous>"
    out = []
    for record in history_records:
        built = scrub.build_record(record, install_id=install)
        if built is not None:
            out.append(built)
    return out
