"""Aggregate the local execution history into engineering signals.

Pure functions over history records (the dicts written by
:mod:`qontinuum.report.history`). They power the enriched ``qont history stats``
today and the trend dashboards in a later phase — one analytics core, many
renderers. Everything degrades gracefully on sparse or old-schema records.
"""

from __future__ import annotations

from collections import defaultdict


def summarize_executions(records: list[dict]) -> dict:
    """A compact analytics snapshot across all recorded runs."""
    if not records:
        return {"runs": 0}
    hw = _hardware_runs(records)
    hw_pass = sum(1 for r in hw if r["status"] == "pass")
    spend = [r["cheapest_usd"] for r in records if r.get("cheapest_usd") is not None]
    suite_pass = sum(1 for r in records if r.get("status") == "pass")
    return {
        "runs": len(records),
        "suite_pass_rate": _rate(suite_pass, len(records)),
        "hardware_runs": len(hw),
        "hardware_success_rate": _rate(hw_pass, len(hw)) if hw else None,
        "providers_used": provider_usage(records) or None,
        "estimated_spend_usd": round(sum(spend), 2) if spend else None,
        "avg_hardware_duration_ms": _avg([r["duration_ms"] for r in hw if r.get("duration_ms")]),
    }


def provider_usage(records: list[dict]) -> dict[str, int]:
    """Count hardware executions per target (e.g. ``ibm_brisbane``)."""
    usage: dict[str, int] = defaultdict(int)
    for test in _hardware_runs(records):
        usage[test["target"]] += 1
    return dict(sorted(usage.items(), key=lambda kv: -kv[1]))


def cost_series(records: list[dict]) -> list[dict]:
    """Time series of the cheapest per-run hardware estimate, for trend charts."""
    return [
        {"at": r["created_at"], "usd": r["cheapest_usd"]}
        for r in records
        if r.get("cheapest_usd") is not None
    ]


def fidelity_series(records: list[dict]) -> list[dict]:
    """Time series of the mean recorded check statistic per run (proxy for drift)."""
    out = []
    for r in records:
        stats = [
            c["statistic"]
            for t in r.get("tests", [])
            for c in t.get("checks", [])
            if c.get("statistic") is not None
        ]
        if stats:
            out.append({"at": r["created_at"], "mean_statistic": round(_avg(stats), 5)})
    return out


def _hardware_runs(records: list[dict]) -> list[dict]:
    """Flatten per-test hardware executions with a parsed target."""
    out = []
    for record in records:
        for test in record.get("tests", []):
            backend = str(test.get("backend", ""))
            if backend.startswith("hw:"):
                out.append({**test, "target": backend[3:]})
    return out


def _rate(numerator: int, denominator: int) -> str | None:
    if not denominator:
        return None
    return f"{numerator / denominator:.1%}"


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None
