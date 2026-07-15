"""The engineering report: the whole intelligence layer in one document.

A single markdown report that answers "where should this run, and why?" —
recommendation, a concrete execution plan, provider health, cost analysis, and
historical context, each with its confidence and assumptions. Pure renderer over
already-computed structured objects, so it is testable and reused by the CLI and
CI. Continues to complement (not replace) the existing suite-result reports.
"""

from __future__ import annotations

from datetime import UTC, datetime

from qontinuum.cost.estimator import CostEstimate
from qontinuum.intelligence.models import (
    ExecutionPlan,
    ProviderHealth,
    Recommendation,
)


def render_engineering_report(
    *,
    workload: str,
    strategy: str,
    recommendations: list[Recommendation],
    plan: ExecutionPlan | None,
    healths: list[ProviderHealth],
    estimates: list[CostEstimate],
    analytics: dict,
    tool_version: str = "",
    generated_at: str | None = None,
) -> str:
    when = generated_at or datetime.now(UTC).isoformat(timespec="seconds")
    lines: list[str] = [
        "# ⚛️ Qontinuum engineering report",
        "",
        f"**Workload:** `{workload}`  ·  **Strategy:** {strategy}  ·  _generated {when}_",
        "",
    ]
    lines += _plan_section(plan)
    lines += _recommendation_section(recommendations)
    lines += _provider_section(healths)
    lines += _cost_section(estimates)
    lines += _history_section(analytics)
    lines += [
        "---",
        f"<sub>qontinuum v{tool_version} · reasoning is rule-based and explainable; "
        "success is a per-shot survival estimate, not a measured fidelity</sub>",
        "",
    ]
    return "\n".join(lines) + "\n"


def _plan_section(plan: ExecutionPlan | None) -> list[str]:
    if plan is None:
        return ["## Execution plan", "", "_No feasible device for this workload._", ""]
    out = [
        "## Execution plan",
        "",
        f"**Selected:** {plan.display} ({plan.provider})  ·  "
        f"**risk:** {plan.risk_level}  ·  **confidence:** {plan.confidence:.0%}",
        "",
        "| Expected runtime | Expected queue | Expected cost | Expected fidelity |",
        "|---|---|---|---|",
        f"| {_secs(plan.estimated_runtime_s)} | {_secs(plan.estimated_queue_s)} "
        f"| {_usd(plan.estimated_cost_usd)} | {_pct(plan.expected_fidelity)} |",
        "",
        f"**Why:** {plan.explanation.summary}",
    ]
    for reason in plan.explanation.reasons:
        out.append(f"- {reason}")
    if plan.risks:
        out += ["", "**Risks:**"] + [f"- ⚠️ {r}" for r in plan.risks]
    if plan.fallbacks:
        out += ["", "**Fallbacks:**"] + [
            f"- {fb.display} — {fb.reason}" for fb in plan.fallbacks
        ]
    if plan.explanation.assumptions:
        out += ["", "**Assumptions:**"] + [f"- {a}" for a in plan.explanation.assumptions]
    if plan.explanation.missing:
        out += ["", "**Missing evidence:**"] + [f"- {m}" for m in plan.explanation.missing]
    out.append("")
    return out


def _recommendation_section(recs: list[Recommendation]) -> list[str]:
    feasible = [r for r in recs if r.feasible][:6]
    if not feasible:
        return []
    out = [
        "## Ranked recommendations",
        "",
        "| # | Device | Provider | Success | Cost | Runtime | Reliability | Risks |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(feasible, 1):
        out.append(
            f"| {i} | {r.display} | {r.provider} | {_pct(r.success_prob)} | "
            f"{_usd(r.usd)} | {_secs(r.runtime_s)} | {_pct(r.reliability)} | {len(r.risks)} |"
        )
    out.append("")
    return out


def _provider_section(healths: list[ProviderHealth]) -> list[str]:
    scored = [h for h in healths if h.reliability is not None][:8]
    if not scored:
        return []
    out = [
        "## Provider analysis",
        "",
        "| Device | Reliability | Calibration | Community | Evidence | Confidence |",
        "|---|---:|---:|---:|---|---:|",
    ]
    for h in scored:
        out.append(
            f"| {h.display} | {_pct(h.reliability)} | {_pct(h.calibration_quality)} | "
            f"{_pct(h.community_success)} | {', '.join(h.data_sources) or '—'} "
            f"| {h.confidence:.0%} |"
        )
    out.append("")
    return out


def _cost_section(estimates: list[CostEstimate]) -> list[str]:
    priced = [e for e in estimates if e.feasible][:8]
    if not priced:
        return []
    out = ["## Cost analysis", "", "| Provider | Device | Estimated |", "|---|---|---:|"]
    for e in priced:
        price = _usd(e.usd) if e.usd is not None else (e.units or "—")
        out.append(f"| {e.provider} | {e.display} | {price} |")
    out.append("")
    return out


def _history_section(analytics: dict) -> list[str]:
    if not analytics or analytics.get("runs", 0) == 0:
        return ["## Historical context", "", "_No local run history yet._", ""]
    rows = {
        "Runs recorded": analytics.get("runs"),
        "Suite pass rate": analytics.get("suite_pass_rate"),
        "Hardware runs": analytics.get("hardware_runs"),
        "Hardware success rate": analytics.get("hardware_success_rate"),
        "Estimated spend": _usd(analytics.get("estimated_spend_usd")),
    }
    out = ["## Historical context", "", "| Metric | Value |", "|---|---|"]
    for label, value in rows.items():
        if value is not None:
            out.append(f"| {label} | {value} |")
    out.append("")
    return out


def _pct(value: float | None) -> str:
    return f"{value:.0%}" if isinstance(value, (int, float)) else "—"


def _usd(value: float | None) -> str:
    return f"${value:,.2f}" if isinstance(value, (int, float)) else "—"


def _secs(value: float | None) -> str:
    return f"{value:,.0f}s" if isinstance(value, (int, float)) else "—"
