"""Execution planning: turn a ranked recommendation into a concrete decision.

A plan names the selected device, its estimated runtime/cost/fidelity, the
risks going in, and ordered fallbacks — everything a human (or, later, an
automated deployer) needs to decide whether and how to execute. It is a thin,
explainable layer over the recommendation engine, not new physics.
"""

from __future__ import annotations

from qontinuum.intelligence.models import (
    ExecutionPlan,
    Explanation,
    Recommendation,
    RejectedOption,
    Strategy,
)


class PlanningError(RuntimeError):
    """No feasible device could be planned for the workload."""


def build_plan(
    recommendations: list[Recommendation],
    *,
    strategy: Strategy,
    workload: str,
    budget: float | None = None,
    max_fallbacks: int = 2,
) -> ExecutionPlan:
    """Select the top recommendation and attach fallbacks + budget verdict."""
    usable = [r for r in recommendations if r.feasible and _within_budget(r, budget)]
    if not usable:
        reason = "no device fits the workload"
        if budget is not None:
            reason += f" within the ${budget:,.2f} budget"
        raise PlanningError(reason)

    top = usable[0]
    fallbacks = [
        RejectedOption(
            provider=r.provider,
            device=r.device,
            display=r.display,
            reason=_fallback_reason(r, top, strategy),
        )
        for r in usable[1 : 1 + max_fallbacks]
    ]
    return ExecutionPlan(
        strategy=strategy.value,
        workload=workload,
        provider=top.provider,
        device=top.device,
        display=top.display,
        estimated_runtime_s=top.runtime_s,
        estimated_cost_usd=top.usd,
        expected_fidelity=top.success_prob,
        within_budget=(None if budget is None else _within_budget(top, budget)),
        risks=top.risks,
        fallbacks=fallbacks,
        explanation=top.explanation or Explanation(summary=f"{top.display} selected."),
    )


def _within_budget(r: Recommendation, budget: float | None) -> bool:
    if budget is None:
        return True
    return r.usd is not None and r.usd <= budget


def _fallback_reason(r: Recommendation, top: Recommendation, strategy: Strategy) -> str:
    if strategy is Strategy.COST and r.usd is not None and top.usd is not None:
        return f"${r.usd - top.usd:,.2f} more than the primary"
    if strategy is Strategy.FIDELITY and r.success_prob is not None and top.success_prob:
        return f"{(top.success_prob - r.success_prob):.0%} lower expected success"
    if strategy is Strategy.SPEED and r.runtime_s and top.runtime_s:
        return f"~{r.runtime_s - top.runtime_s:,.0f}s slower"
    if r.reliability is not None:
        return f"reliability {r.reliability:.0%}; use if the primary is unavailable"
    return "next best option if the primary is unavailable"
