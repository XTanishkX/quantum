"""Wire schema for the Quantum Intelligence Network — and its privacy contract.

The single most important property here is the **allowlist**: a telemetry record
can only ever contain the fields declared on :class:`TelemetryRecord`. Circuits,
probability distributions, snapshots, counts, test ids, file paths, git shas,
seeds, credentials, and API keys have no field to live in and are never
constructed — see :mod:`qontinuum.telemetry.scrub`.

Everything is versioned (:data:`TELEMETRY_SCHEMA`) and integrity-checked (a
sha256 over the canonical record) so a receiver can validate and evolve the
format without ambiguity.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field

TELEMETRY_SCHEMA = 1
COMMUNITY_SCHEMA = 1


def bucket(value: int, edges: tuple[int, ...]) -> str:
    """Coarsen a count into a labelled bucket to limit fingerprinting.

    ``bucket(7, (10, 50, 100))`` → ``"1-10"``; ``bucket(250, (10, 50, 100))`` →
    ``"100+"``. Buckets are how structural sizes (shots, gate counts) are shared
    without revealing exact values.
    """
    lo = 1
    for hi in edges:
        if value <= hi:
            return f"{lo}-{hi}"
        lo = hi + 1
    return f"{edges[-1] + 1}+"


class TelemetryRecord(BaseModel):
    """One anonymous hardware-execution datapoint. This is the *entire* payload.

    No field carries source, circuits, distributions, or identity beyond a
    random, user-generated ``install_id`` that maps to nothing.
    """

    schema_version: int = TELEMETRY_SCHEMA
    record_id: str  # random uuid4, unique per record
    install_id: str  # random uuid4, generated on opt-in
    tool_version: str = ""
    ts_day: str = ""  # UTC calendar day only (no time-of-day)
    mode: str = "hardware"
    provider: str | None = None  # public catalog provider id
    device: str | None = None  # public catalog device id
    shots_bucket: str | None = None
    outcome: str | None = None  # pass | fail | error
    runtime_s: float | None = None
    queue_time_s: float | None = None
    estimated_cost_usd: float | None = None
    calibration_age_days: int | None = None
    routing_strategy: str | None = None
    checksum: str = ""  # sha256 over the canonical record (checksum field empty)

    def canonical(self) -> str:
        """Deterministic JSON with the checksum field blanked, for hashing."""
        data = self.model_dump()
        data["checksum"] = ""
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def sign(self) -> TelemetryRecord:
        """Return a copy with ``checksum`` set to the record's sha256."""
        digest = hashlib.sha256(self.canonical().encode()).hexdigest()
        return self.model_copy(update={"checksum": digest})

    def verify(self) -> bool:
        return bool(self.checksum) and (
            hashlib.sha256(self.canonical().encode()).hexdigest() == self.checksum
        )


class CommunityDeviceStat(BaseModel):
    """Aggregated community reliability for one device (no raw records)."""

    samples: int = 0
    success_rate: float | None = None
    avg_runtime_s: float | None = None
    avg_queue_s: float | None = None
    avg_cost_usd: float | None = None


class CommunityAggregate(BaseModel):
    """A community-intelligence snapshot: per-device aggregates only.

    This is what the network returns and what Qontinuum caches locally. It never
    contains individual records — only counts and averages — so it is safe to
    distribute and cannot be traced to a contributor.
    """

    schema_version: int = COMMUNITY_SCHEMA
    generated_at: str = ""
    source: str = "community"
    devices: dict[str, CommunityDeviceStat] = Field(default_factory=dict)

    def is_compatible(self) -> bool:
        return self.schema_version == COMMUNITY_SCHEMA
