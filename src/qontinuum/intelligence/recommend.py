"""The recommendation engine: rank devices for a workload, and explain why.

It builds on the router's transparent success-x-cost scoring
(:mod:`qontinuum.router`) and adds runtime estimation, provider-health
reliability, and per-strategy ranking. Every recommendation carries an
:class:`~qontinuum.intelligence.models.Explanation` — the engine never returns a
score without the reasoning, assumptions, and missing evidence behind it.

Pure functions over already-gathered inputs (profiles, cost estimates, catalog,
health). No CLI, no I/O — so it is trivially testable and reusable by reports,
the planner, and a future hosted platform.
"""

from __future__ import annotations

from qontinuum.cost.analysis import CircuitProfile
from qontinuum.cost.estimator import CostEstimate
from qontinuum.intelligence.health import assess_health, health_by_device
from qontinuum.intelligence.models import (
    Explanation,
    ProviderHealth,
    Recommendation,
    Strategy,
)
from qontinuum.router import score_devices

# Fallback runtime model for devices the catalog does not price by the second.
# Deliberately coarse and labeled as an estimate wherever it surfaces.
_DEFAULT_RUNTIME = {"overhead_s": 5.0, "per_shot_s": 0.0008, "per_layer_s": 2e-5}

_STRATEGY_WEIGHTS = {  # for BALANCED: how much each normalized dimension counts
    "fidelity": 0.35,
    "value": 0.30,
    "reliability": 0.20,
    "speed": 0.15,
}

_INF = float("inf")


def estimate_runtime_s(profile: CircuitProfile, shots: int, device: dict) -> float:
    """Parametric wall-clock estimate for one device (queue time excluded)."""
    rt = device.get("runtime") or _DEFAULT_RUNTIME
    seconds = rt["overhead_s"] + shots * (rt["per_shot_s"] + profile.depth * rt["per_layer_s"])
    return round(seconds, 3)


def recommend(
    profiles: list[CircuitProfile],
    shots: list[int],
    estimates: list[CostEstimate],
    catalog: dict,
    *,
    strategy: Strategy = Strategy.BALANCED,
    budget: float | None = None,
    health: list[ProviderHealth] | None = None,
) -> list[Recommendation]:
    """Rank devices for a workload under ``strategy``, best first."""
    if health is None:
        health = assess_health(catalog)
    health_map = health_by_device(health)
    device_by_id = {
        device_id: device
        for provider in catalog.get("providers", {}).values()
        for device_id, device in provider.get("devices", {}).items()
    }
    worst = max(profiles, key=lambda p: p.depth) if profiles else None
    total_shots = sum(shots)

    scores = score_devices(profiles, estimates, catalog)
    recs: list[Recommendation] = []
    for s in scores:
        device = device_by_id.get(s.device, {})
        runtime = (
            estimate_runtime_s(worst, total_shots, device)
            if (worst and s.feasible)
            else None
        )
        h = health_map.get(s.device)
        reliability = h.reliability if h else None
        recs.append(
            Recommendation(
                strategy=strategy.value,
                provider=s.provider,
                device=s.device,
                display=s.display,
                feasible=s.feasible,
                success_prob=s.success_prob,
                usd=s.usd,
                usd_per_success=s.usd_per_success,
                runtime_s=runtime,
                reliability=reliability,
                risks=_risks(s, h, budget),
            )
        )

    _rank(recs, strategy=strategy, budget=budget)
    _explain(recs, strategy=strategy, budget=budget, health_map=health_map)
    return recs


def _risks(score, health: ProviderHealth | None, budget: float | None) -> list[str]:
    risks: list[str] = []
    if not score.feasible:
        risks.append(score.note or "circuit does not fit this device")
        return risks
    if score.success_prob is not None and score.success_prob < 0.5:
        risks.append(
            f"low expected success ({score.success_prob:.0%}) — the circuit is deep "
            "relative to this device's noise"
        )
    if score.usd is None:
        risks.append("no public dollar rate — cost and budget cannot be enforced")
    if health is None or health.reliability is None:
        risks.append("no reliability evidence for this device")
    elif health.calibration_age_days is not None and health.calibration_age_days > 90:
        risks.append(f"calibration data is {health.calibration_age_days} days old")
    if budget is not None and score.usd is not None and score.usd > budget:
        risks.append(f"estimated ${score.usd:,.2f} exceeds the ${budget:,.2f} budget")
    return risks


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #
def _rank(recs: list[Recommendation], *, strategy: Strategy, budget: float | None) -> None:
    feasible = [r for r in recs if r.feasible and _within_budget(r, budget)]
    if strategy is Strategy.BALANCED:
        _score_balanced(feasible)
    else:
        for r in feasible:
            r.score = _single_metric(r, strategy)
    # Infeasible / over-budget candidates always sort last, by name for stability.
    recs.sort(key=lambda r: (not (r.feasible and _within_budget(r, budget)),
                             r.score if r.score is not None else _INF, r.display))


def _within_budget(r: Recommendation, budget: float | None) -> bool:
    if budget is None:
        return True
    return r.usd is not None and r.usd <= budget


def _single_metric(r: Recommendation, strategy: Strategy) -> float:
    if strategy is Strategy.COST:
        return r.usd if r.usd is not None else _INF
    if strategy is Strategy.VALUE:
        return r.usd_per_success if r.usd_per_success is not None else _INF
    if strategy is Strategy.SPEED:
        return r.runtime_s if r.runtime_s is not None else _INF
    if strategy is Strategy.FIDELITY:
        return -r.success_prob if r.success_prob is not None else _INF
    if strategy is Strategy.RELIABILITY:
        return -r.reliability if r.reliability is not None else _INF
    raise ValueError(f"unhandled strategy {strategy!r}")  # pragma: no cover


def _score_balanced(feasible: list[Recommendation]) -> None:
    """Composite of normalized fidelity, value, reliability, and speed badness."""
    dims = {
        "fidelity": [_neg(r.success_prob) for r in feasible],
        "value": [r.usd_per_success for r in feasible],
        "reliability": [_neg(r.reliability) for r in feasible],
        "speed": [r.runtime_s for r in feasible],
    }
    norms = {name: _normalize(values) for name, values in dims.items()}
    for i, r in enumerate(feasible):
        r.score = round(
            sum(_STRATEGY_WEIGHTS[name] * norms[name][i] for name in _STRATEGY_WEIGHTS), 4
        )


def _neg(value: float | None) -> float | None:
    """Turn a higher-is-better metric into a lower-is-better one."""
    return None if value is None else -value


def _normalize(values: list[float | None]) -> list[float]:
    """Min-max each value to [0,1] badness; missing data is treated as worst (1)."""
    present = [v for v in values if v is not None]
    if not present:
        return [1.0] * len(values)
    lo, hi = min(present), max(present)
    span = hi - lo
    return [1.0 if v is None else (0.0 if span == 0 else (v - lo) / span) for v in values]


# --------------------------------------------------------------------------- #
# Explanation
# --------------------------------------------------------------------------- #
def _explain(
    recs: list[Recommendation],
    *,
    strategy: Strategy,
    budget: float | None,
    health_map: dict[str, ProviderHealth],
) -> None:
    feasible = [r for r in recs if r.feasible and _within_budget(r, budget)]
    winner = feasible[0] if feasible else None
    for r in recs:
        r.explanation = _explain_one(
            r, winner=winner, strategy=strategy, budget=budget, health=health_map.get(r.device)
        )


def _explain_one(
    r: Recommendation,
    *,
    winner: Recommendation | None,
    strategy: Strategy,
    budget: float | None,
    health: ProviderHealth | None,
) -> Explanation:
    reasons: list[str] = []
    assumptions = [
        "expected success is a per-shot survival estimate from median error "
        "rates, not a measured fidelity",
    ]
    missing: list[str] = []

    if not r.feasible:
        return Explanation(
            summary=f"{r.display} was ruled out: {r.risks[0] if r.risks else 'not feasible'}.",
            reasons=r.risks,
            confidence=0.9,
        )
    if budget is not None and not _within_budget(r, budget):
        return Explanation(
            summary=f"{r.display} was excluded by the ${budget:,.2f} budget.",
            reasons=[risk for risk in r.risks if "budget" in risk] or ["over budget"],
            confidence=0.9,
        )

    is_winner = winner is not None and r.device == winner.device
    verb = "is the" if is_winner else "is a candidate"
    reasons.append(_headline_reason(r, strategy))
    if r.reliability is not None:
        reasons.append(f"reliability {r.reliability:.0%} ({_health_basis(health)})")
    if r.runtime_s is not None:
        reasons.append(f"estimated runtime ~{r.runtime_s:,.0f}s (queue time not modeled)")
        assumptions.append(
            "runtime is a parametric estimate; provider queue time is offline-unknown"
        )
    for risk in r.risks:
        missing_hint = risk if ("no " in risk or "stale" in risk) else None
        if missing_hint:
            missing.append(missing_hint)

    if health is None or not health.data_sources:
        missing.append("no calibration or history evidence for this device")
    confidence = round(0.4 + 0.6 * (health.confidence if health else 0.0), 3)

    summary = f"{r.display} {verb} {strategy.value} pick for this workload."
    return Explanation(
        summary=summary,
        reasons=reasons,
        assumptions=assumptions,
        missing=sorted(set(missing)),
        confidence=confidence,
    )


def _headline_reason(r: Recommendation, strategy: Strategy) -> str:
    if strategy is Strategy.COST:
        return f"lowest estimated cost (${r.usd:,.2f})" if r.usd is not None else "no priced cost"
    if strategy is Strategy.VALUE:
        return (
            f"best value at ${r.usd_per_success:,.2f} per successful shot"
            if r.usd_per_success is not None
            else "value not priceable (no dollar rate)"
        )
    if strategy is Strategy.SPEED:
        if r.runtime_s:
            return f"fastest estimated runtime (~{r.runtime_s:,.0f}s)"
        return "runtime unknown"
    if strategy is Strategy.FIDELITY:
        return (
            f"highest expected success ({r.success_prob:.0%})"
            if r.success_prob is not None
            else "no quality data to judge fidelity"
        )
    if strategy is Strategy.RELIABILITY:
        return (
            f"most reliable ({r.reliability:.0%} composite)"
            if r.reliability is not None
            else "no reliability evidence"
        )
    # BALANCED
    return "best balance of fidelity, value, reliability, and speed"


def _health_basis(health: ProviderHealth | None) -> str:
    if health is None or not health.data_sources:
        return "no evidence"
    return " + ".join(health.data_sources)
