"""Execution intelligence: reason about *where* to run quantum work, and why.

The engine turns a workload plus the evidence Qontinuum already has — the cost
catalog, calibration quality, and local run history — into explainable
recommendations and execution plans. It is pure and provider-agnostic: it reads
the plugin-extensible catalog, never hardcoded providers, and every output is a
structured model in :mod:`qontinuum.intelligence.models` with the reasoning
attached.

Public API::

    from qontinuum.intelligence import assess_health, recommend, build_plan, Strategy
"""

from qontinuum.intelligence.analytics import (
    cost_series,
    fidelity_series,
    provider_usage,
    summarize_executions,
)
from qontinuum.intelligence.health import assess_health, health_by_device
from qontinuum.intelligence.models import (
    ExecutionPlan,
    Explanation,
    ProviderHealth,
    Recommendation,
    RejectedOption,
    Strategy,
)
from qontinuum.intelligence.planning import PlanningError, build_plan
from qontinuum.intelligence.recommend import estimate_runtime_s, recommend

__all__ = [
    "ExecutionPlan",
    "Explanation",
    "PlanningError",
    "ProviderHealth",
    "Recommendation",
    "RejectedOption",
    "Strategy",
    "assess_health",
    "build_plan",
    "cost_series",
    "estimate_runtime_s",
    "fidelity_series",
    "health_by_device",
    "provider_usage",
    "recommend",
    "summarize_executions",
]
