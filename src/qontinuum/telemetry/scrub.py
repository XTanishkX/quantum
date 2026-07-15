"""Turn a local history record into an anonymous telemetry record — safely.

This module is the privacy boundary. It reads history records (which *do*
contain sensitive data — circuit hashes, counts, test ids, git shas) and emits
:class:`TelemetryRecord` objects built by **explicitly copying a fixed allowlist
of fields**. It never spreads a source dict, so a field that isn't named here
cannot leak, even if a future history schema adds one.

Only hardware executions are captured — community intelligence is about real
devices, and simulator runs carry no provider signal.
"""

from __future__ import annotations

import uuid

from qontinuum.telemetry.schema import TelemetryRecord, bucket

_SHOTS_EDGES = (100, 1000, 4000, 10000, 50000)


def build_record(
    history_record: dict, *, install_id: str, tool_version: str | None = None
) -> TelemetryRecord | None:
    """Build one signed telemetry record from a hardware history record.

    Returns ``None`` for simulator runs or records without an execution block —
    there is nothing device-related to contribute.
    """
    execution = history_record.get("execution")
    if not isinstance(execution, dict) or execution.get("mode") != "hardware":
        return None

    total_shots = _int_or_none(history_record.get("total_shots"))
    shots_bucket = bucket(total_shots, _SHOTS_EDGES) if total_shots else None

    record = TelemetryRecord(
        record_id=str(uuid.uuid4()),
        install_id=install_id,
        tool_version=str(tool_version or history_record.get("tool_version") or ""),
        ts_day=_day(history_record.get("created_at")),
        mode="hardware",
        # provider/device are public catalog identifiers, never private
        provider=_str_or_none(execution.get("provider")),
        device=_str_or_none(execution.get("target")),
        shots_bucket=shots_bucket,
        outcome=_str_or_none(execution.get("outcome") or history_record.get("status")),
        runtime_s=_round(execution.get("runtime_s")),
        queue_time_s=_round(execution.get("queue_time_s")),
        estimated_cost_usd=_round(execution.get("estimated_cost_usd")),
        calibration_age_days=_int_or_none(execution.get("calibration_age_days")),
        routing_strategy=_str_or_none(execution.get("routing_strategy")),
    )
    return record.sign()


def _day(created_at) -> str:
    """Keep the calendar day only — drop time-of-day to limit fingerprinting."""
    if not isinstance(created_at, str):
        return ""
    return created_at[:10]


def _str_or_none(value) -> str | None:
    return str(value) if isinstance(value, str) and value else None


def _int_or_none(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _round(value) -> float | None:
    return round(float(value), 3) if isinstance(value, (int, float)) and not isinstance(
        value, bool
    ) else None
