"""Provider health: how much a device can be trusted to run work well.

Two evidence sources, combined and always attributed:

- **Calibration** (offline, always available): the catalog's published median
  error rates give a per-device quality proxy and a freshness age.
- **History** (offline, when present): local hardware runs give an empirical
  success rate and average duration for devices we have actually used.

When a signal is missing it stays ``None`` — the engine never invents numbers,
it lowers ``confidence`` and records what evidence it lacked. Health is derived
from the (plugin-extensible) catalog, so it works for any provider.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from qontinuum.intelligence.models import ProviderHealth

# Runs below this count are too few to trust as an empirical success rate.
_MIN_EMPIRICAL_RUNS = 3


def assess_health(
    catalog: dict,
    records: list[dict] | None = None,
    *,
    now: datetime | None = None,
    community: object | None = None,
) -> list[ProviderHealth]:
    """One :class:`ProviderHealth` per catalog device.

    ``community`` is an optional :class:`~qontinuum.telemetry.schema.CommunityAggregate`
    (or anything exposing ``.devices``): when present, each device blends in the
    network's success rate, attributed as a ``community`` data source. It is
    always additive — omitting it reproduces the offline, catalog+history result.
    """
    now = now or datetime.now(UTC)
    age_days = _catalog_age_days(catalog, now)
    empirical = _empirical_by_device(records or [], catalog)
    community_devices = _community_by_device(getattr(community, "devices", {}) or {}, catalog)

    out: list[ProviderHealth] = []
    for provider in catalog.get("providers", {}).values():
        for device_id, device in provider.get("devices", {}).items():
            out.append(
                _assess_device(
                    provider["display"], device_id, device, age_days,
                    empirical.get(device_id), community_devices.get(device_id),
                )
            )
    out.sort(key=lambda h: (-(h.reliability or -1.0), h.device))
    return out


def _community_by_device(community_devices: dict, catalog: dict) -> dict:
    """Map community keys (run targets) onto catalog device ids leniently.

    Contributors key stats by their run target (e.g. ``braket:rigetti_cepheus``),
    while the catalog and health use the device id (``rigetti_cepheus``); the same
    token-overlap match used for local history reconciles the two.
    """
    device_ids = [
        device_id
        for provider in catalog.get("providers", {}).values()
        for device_id in provider.get("devices", {})
    ]
    out: dict = {}
    for key, stat in community_devices.items():
        matched = key if key in device_ids else _match_device(str(key), device_ids)
        if matched is not None:
            out[matched] = stat
    return out


def health_by_device(healths: list[ProviderHealth]) -> dict[str, ProviderHealth]:
    """Index health rows by catalog device id (matches ``RouteScore.device``)."""
    return {h.device: h for h in healths}


def _assess_device(
    provider_display: str,
    device_id: str,
    device: dict,
    age_days: int | None,
    empirical: dict | None,
    community: object | None = None,
) -> ProviderHealth:
    quality = device.get("quality") or {}
    calibration_quality = _calibration_quality(quality)
    sources: list[str] = []
    notes: list[str] = []

    if calibration_quality is not None:
        sources.append("catalog")
    else:
        notes.append("no published error rates in the catalog")

    emp_success = None
    avg_duration = None
    runs = failures = 0
    if empirical:
        runs = empirical["runs"]
        failures = empirical["failures"]
        avg_duration = empirical["avg_duration_ms"]
        if runs >= _MIN_EMPIRICAL_RUNS:
            emp_success = (runs - failures) / runs
            sources.append("history")
        else:
            notes.append(f"only {runs} local run(s) — too few for an empirical rate")

    community_success = None
    community_samples = int(getattr(community, "samples", 0) or 0)
    if community is not None and community_samples > 0:
        community_success = getattr(community, "success_rate", None)
        if community_success is not None:
            sources.append("community")

    reliability, confidence = _combine(
        calibration_quality, emp_success, runs, community_success, community_samples,
        age_days, notes,
    )

    return ProviderHealth(
        provider=provider_display,
        device=device_id,
        display=device.get("display", device_id),
        reliability=reliability,
        calibration_quality=calibration_quality,
        empirical_success=emp_success,
        community_success=community_success,
        community_samples=community_samples,
        avg_duration_ms=avg_duration,
        recent_runs=runs,
        recent_failures=failures,
        calibration_age_days=age_days,
        data_sources=sources,
        confidence=round(confidence, 3),
        notes=notes,
    )


def _calibration_quality(quality: dict) -> float | None:
    """A 0..1 two-qubit + readout survival proxy (higher is better)."""
    e2q = quality.get("error_2q")
    er = quality.get("error_readout")
    if e2q is None and er is None:
        return None
    survival = 1.0
    if e2q is not None:
        survival *= 1.0 - e2q
    if er is not None:
        survival *= 1.0 - er
    return round(max(0.0, min(1.0, survival)), 4)


def _combine(
    calibration_quality: float | None,
    empirical_success: float | None,
    runs: int,
    community_success: float | None,
    community_samples: int,
    age_days: int | None,
    notes: list[str],
) -> tuple[float | None, float]:
    """Blend calibration, local history, and community into reliability + confidence.

    Each available signal contributes a value and a weight; reliability is their
    weighted average. Calibration is a fixed-weight prior; local history and
    community intelligence gain weight (and confidence) with their sample sizes.
    """
    if calibration_quality is None and empirical_success is None and community_success is None:
        notes.append("no calibration or history evidence — reliability unknown")
        return None, 0.1

    signals: list[tuple[float, float]] = []
    confidence = 0.0

    if calibration_quality is not None:
        signals.append((calibration_quality, 0.5))
        confidence += 0.5
        if age_days is not None and age_days > 90:
            confidence -= 0.15
            notes.append(f"calibration data is {age_days} days old")

    if empirical_success is not None:
        w = min(1.0, runs / 20)
        signals.append((empirical_success, max(0.1, w)))
        confidence += 0.4 * w
    elif calibration_quality is not None and community_success is None:
        notes.append("reliability is calibration-only (no local run history)")

    if community_success is not None:
        wc = min(1.0, community_samples / 50)
        signals.append((community_success, 0.3 * max(0.1, wc)))
        confidence += 0.2 * wc

    total_weight = sum(w for _, w in signals)
    reliability = sum(v * w for v, w in signals) / total_weight if total_weight else None

    return (round(reliability, 4) if reliability is not None else None), round(
        max(0.1, min(1.0, confidence)), 3
    )


def _catalog_age_days(catalog: dict, now: datetime) -> int | None:
    verified = catalog.get("verified")
    if not verified:
        return None
    try:
        when = datetime.fromisoformat(str(verified)).replace(tzinfo=UTC)
    except ValueError:
        return None
    return (now - when).days


def _empirical_by_device(records: list[dict], catalog: dict) -> dict[str, dict]:
    """Aggregate local hardware runs onto catalog device ids, best-effort.

    History records tests with ``backend == "hw:<target>"``. We match the
    target string against catalog device ids and display names leniently; a run
    we cannot attribute is simply dropped (health degrades, never lies).
    """
    device_ids = [
        device_id
        for provider in catalog.get("providers", {}).values()
        for device_id in provider.get("devices", {})
    ]
    agg: dict[str, dict] = {}
    for record in records:
        for test in record.get("tests", []):
            backend = str(test.get("backend", ""))
            if not backend.startswith("hw:"):
                continue
            device_id = _match_device(backend[3:], device_ids)
            if device_id is None:
                continue
            bucket = agg.setdefault(
                device_id, {"runs": 0, "failures": 0, "duration_sum": 0.0, "duration_n": 0}
            )
            bucket["runs"] += 1
            if test.get("status") != "pass":
                bucket["failures"] += 1
            dur = test.get("duration_ms")
            if isinstance(dur, (int, float)):
                bucket["duration_sum"] += dur
                bucket["duration_n"] += 1
    for bucket in agg.values():
        bucket["avg_duration_ms"] = (
            round(bucket["duration_sum"] / bucket["duration_n"], 3)
            if bucket["duration_n"]
            else None
        )
    return agg


def _match_device(target: str, device_ids: list[str]) -> str | None:
    """Lenient map from a hardware target string to a catalog device id."""
    tokens = set(re.split(r"[^a-z0-9]+", target.lower()))
    tokens.discard("")
    best: tuple[int, str] | None = None
    for device_id in device_ids:
        parts = set(re.split(r"[^a-z0-9]+", device_id.lower()))
        overlap = len(tokens & parts)
        if overlap and (best is None or overlap > best[0]):
            best = (overlap, device_id)
    return best[1] if best else None
