"""Structured outputs of the execution-intelligence engine.

These models are the stable contract other layers consume — the CLI, reports,
and (later) the dashboard and a hosted platform. They are deliberately free of
any presentation logic: an engine produces them, a renderer displays them.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Strategy(StrEnum):
    """What an execution recommendation optimizes for."""

    COST = "cost"
    FIDELITY = "fidelity"
    SPEED = "speed"
    VALUE = "value"  # dollars per successful shot
    RELIABILITY = "reliability"
    BALANCED = "balanced"

    @classmethod
    def parse(cls, value: str) -> Strategy:
        try:
            return cls(value.lower())
        except ValueError as exc:
            options = ", ".join(s.value for s in cls)
            raise ValueError(f"unknown strategy {value!r}; choose one of: {options}") from exc


class ProviderHealth(BaseModel):
    """A device's fitness to run work, from calibration data and local history.

    Every numeric signal is optional: when the evidence for it is missing the
    field is ``None`` rather than a fabricated number, and ``confidence`` and
    ``data_sources`` record how much the assessment can be trusted.
    """

    provider: str
    device: str
    display: str
    reliability: float | None = None  # 0..1 composite fitness
    calibration_quality: float | None = None  # 0..1 from published error rates
    empirical_success: float | None = None  # 0..1 from local hardware history
    avg_duration_ms: float | None = None
    recent_runs: int = 0
    recent_failures: int = 0
    calibration_age_days: int | None = None
    data_sources: list[str] = Field(default_factory=list)
    confidence: float = 0.0  # 0..1 — how much evidence backs this row
    notes: list[str] = Field(default_factory=list)


class Explanation(BaseModel):
    """Why a recommendation was made, in plain engineering language."""

    summary: str
    reasons: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)  # evidence we did not have
    confidence: float = 0.0  # 0..1


class RejectedOption(BaseModel):
    """A candidate that lost, with a one-line reason it was not chosen."""

    provider: str
    device: str
    display: str
    reason: str


class Recommendation(BaseModel):
    """A ranked execution candidate for a workload under one strategy."""

    strategy: str
    provider: str
    device: str
    display: str
    feasible: bool = True
    success_prob: float | None = None
    usd: float | None = None
    usd_per_success: float | None = None
    runtime_s: float | None = None
    reliability: float | None = None
    risks: list[str] = Field(default_factory=list)
    score: float | None = None  # the strategy's ranking metric (lower = better)
    explanation: Explanation | None = None


class ExecutionPlan(BaseModel):
    """A concrete pre-execution decision: what to run where, and the fallbacks."""

    strategy: str
    workload: str
    provider: str
    device: str
    display: str
    estimated_runtime_s: float | None = None
    estimated_cost_usd: float | None = None
    expected_fidelity: float | None = None
    within_budget: bool | None = None
    risks: list[str] = Field(default_factory=list)
    fallbacks: list[RejectedOption] = Field(default_factory=list)
    explanation: Explanation
