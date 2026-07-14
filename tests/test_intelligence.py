"""Execution-intelligence engine: health, recommendations, planning, analytics."""

from __future__ import annotations

import json

import pytest
from qiskit import QuantumCircuit
from typer.testing import CliRunner

from qontinuum.cli import app
from qontinuum.cost import estimate_suite, load_catalog, profile_circuit
from qontinuum.intelligence import (
    PlanningError,
    Strategy,
    assess_health,
    build_plan,
    provider_usage,
    recommend,
    summarize_executions,
)


def _workload(qc: QuantumCircuit, shots: int = 2000):
    catalog = load_catalog()
    profiles = [profile_circuit(qc)]
    estimates = estimate_suite([(qc, shots)])
    return profiles, [shots], estimates, catalog


def bell() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


def hw_history(target: str, outcomes: list[str]) -> list[dict]:
    return [
        {
            "created_at": f"2026-07-1{i}T00:00:00",
            "status": outcome,
            "cheapest_usd": 0.5,
            "tests": [
                {"id": "t::a", "status": outcome, "backend": f"hw:{target}",
                 "duration_ms": 1200.0, "checks": [{"name": "c", "statistic": 0.03}]}
            ],
        }
        for i, outcome in enumerate(outcomes)
    ]


# --------------------------------------------------------------------------- #
# Provider health
# --------------------------------------------------------------------------- #
class TestHealth:
    def test_calibration_only_health(self):
        healths = assess_health(load_catalog())
        assert healths
        h = healths[0]
        assert h.data_sources == ["catalog"]
        assert 0 <= h.calibration_quality <= 1
        assert h.reliability == h.calibration_quality  # no history -> calibration only
        assert h.empirical_success is None
        assert 0 < h.confidence <= 1

    def test_history_adds_empirical_signal(self):
        records = hw_history("braket:rigetti_cepheus", ["pass", "pass", "fail", "pass"])
        healths = assess_health(load_catalog(), records)
        rigetti = next(h for h in healths if h.device == "rigetti_cepheus")
        assert "history" in rigetti.data_sources
        assert rigetti.empirical_success == pytest.approx(0.75)
        assert rigetti.recent_runs == 4 and rigetti.recent_failures == 1
        assert rigetti.avg_duration_ms == pytest.approx(1200.0)
        # confidence should exceed a calibration-only row
        calib_only = next(h for h in healths if h.device != "rigetti_cepheus")
        assert rigetti.confidence > calib_only.confidence

    def test_too_few_runs_stay_calibration_only(self):
        records = hw_history("braket:rigetti_cepheus", ["pass", "fail"])  # < 3
        healths = assess_health(load_catalog(), records)
        rigetti = next(h for h in healths if h.device == "rigetti_cepheus")
        assert rigetti.empirical_success is None
        assert "history" not in rigetti.data_sources

    def test_missing_quality_degrades_gracefully(self):
        catalog = {
            "verified": "2026-07-12",
            "providers": {"x": {"display": "X", "devices": {"d": {"display": "D", "qubits": 5}}}},
        }
        (h,) = assess_health(catalog)
        assert h.reliability is None
        assert h.calibration_quality is None
        assert h.confidence == pytest.approx(0.1)
        assert any("no calibration or history" in n for n in h.notes)


# --------------------------------------------------------------------------- #
# Recommendations
# --------------------------------------------------------------------------- #
class TestRecommend:
    def _recs(self, strategy, **kw):
        p, s, e, c = _workload(bell())
        return recommend(p, s, e, c, strategy=strategy, **kw)

    def test_cost_picks_cheapest_feasible(self):
        recs = self._recs(Strategy.COST)
        feasible = [r for r in recs if r.feasible and r.usd is not None]
        assert feasible[0].usd == min(r.usd for r in feasible)

    def test_fidelity_picks_highest_success(self):
        recs = self._recs(Strategy.FIDELITY)
        feasible = [r for r in recs if r.feasible and r.success_prob is not None]
        assert feasible[0].success_prob == max(r.success_prob for r in feasible)

    def test_speed_picks_fastest(self):
        recs = self._recs(Strategy.SPEED)
        feasible = [r for r in recs if r.feasible and r.runtime_s is not None]
        assert feasible[0].runtime_s == min(r.runtime_s for r in feasible)

    def test_every_recommendation_is_explained(self):
        for r in self._recs(Strategy.BALANCED):
            assert r.explanation is not None
            assert r.explanation.summary
            assert 0 <= r.explanation.confidence <= 1

    def test_budget_excludes_pricey_devices(self):
        # Rigetti Cepheus prices a 2000-shot bell at ~$1.15; $1.50 admits it
        # while excluding the pricier trapped-ion devices.
        recs = self._recs(Strategy.VALUE, budget=1.50)
        priced = [r for r in recs if r.usd is not None and r.usd <= 1.50]
        assert priced, "expected at least one device within the $1.50 budget"
        assert recs[0].usd is not None and recs[0].usd <= 1.50
        # a device that exists but exceeds the budget must not be the pick
        assert any(r.usd is not None and r.usd > 1.50 for r in recs)

    def test_all_strategies_produce_a_pick(self):
        for strat in Strategy:
            recs = self._recs(strat)
            assert any(r.feasible for r in recs)

    def test_oversized_circuit_is_infeasible(self):
        big = QuantumCircuit(500)
        big.h(range(500))
        big.measure_all()
        p, s, e, c = _workload(big)
        recs = recommend(p, s, e, c, strategy=Strategy.BALANCED)
        assert all(not r.feasible for r in recs)
        assert recs[0].explanation.summary  # still explained


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #
class TestPlanning:
    def test_plan_selects_top_and_fallbacks(self):
        p, s, e, c = _workload(bell())
        recs = recommend(p, s, e, c, strategy=Strategy.VALUE)
        plan = build_plan(recs, strategy=Strategy.VALUE, workload="demo")
        assert plan.device == recs[0].device
        assert len(plan.fallbacks) == 2
        assert plan.explanation.summary
        # fallbacks are distinct from the primary
        assert all(fb.device != plan.device for fb in plan.fallbacks)

    def test_plan_raises_when_nothing_feasible(self):
        big = QuantumCircuit(500)
        big.h(range(500))
        big.measure_all()
        p, s, e, c = _workload(big)
        recs = recommend(p, s, e, c, strategy=Strategy.BALANCED)
        with pytest.raises(PlanningError, match="no device fits"):
            build_plan(recs, strategy=Strategy.BALANCED, workload="demo")

    def test_plan_raises_when_over_budget(self):
        p, s, e, c = _workload(bell())
        recs = recommend(p, s, e, c, strategy=Strategy.COST, budget=0.001)
        with pytest.raises(PlanningError, match="budget"):
            build_plan(recs, strategy=Strategy.COST, workload="demo", budget=0.001)


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
class TestAnalytics:
    def test_summary_of_empty_history(self):
        assert summarize_executions([]) == {"runs": 0}

    def test_provider_usage_counts_hardware_runs(self):
        records = hw_history("ibm_brisbane", ["pass", "pass"]) + hw_history(
            "braket:ionq_forte", ["fail"]
        )
        usage = provider_usage(records)
        assert usage == {"ibm_brisbane": 2, "braket:ionq_forte": 1}

    def test_summary_hardware_success_rate(self):
        records = hw_history("ibm_brisbane", ["pass", "pass", "fail", "pass"])
        summary = summarize_executions(records)
        assert summary["hardware_runs"] == 4
        assert summary["hardware_success_rate"] == "75.0%"
        assert summary["estimated_spend_usd"] == pytest.approx(2.0)

    def test_provider_comparison(self):
        from qontinuum.intelligence import provider_comparison

        records = hw_history("braket:ionq_forte", ["pass", "pass", "fail", "pass"])
        (row,) = provider_comparison(records)
        assert row["target"] == "braket:ionq_forte"
        assert row["runs"] == 4
        assert row["success_rate"] == pytest.approx(0.75)
        assert row["avg_duration_ms"] == pytest.approx(1200.0)

    def test_routing_decisions_from_execution_records(self):
        from qontinuum.intelligence import routing_decisions

        records = [
            {"created_at": "2026-07-12T00:00:00", "status": "pass",
             "execution": {"mode": "hardware", "target": "braket:ionq_forte",
                           "routing_strategy": "fidelity", "outcome": "pass"},
             "tests": []},
            {"created_at": "2026-07-12T00:00:00", "status": "pass",
             "execution": None, "tests": []},  # simulator run: ignored
        ]
        decisions = routing_decisions(records)
        assert len(decisions) == 1
        assert decisions[0]["strategy"] == "fidelity"
        assert decisions[0]["target"] == "braket:ionq_forte"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
class TestIntelCli:
    def setup_method(self):
        self.runner = CliRunner()

    def test_recommend_table(self, mini_project):
        result = self.runner.invoke(app, ["recommend", str(mini_project)])
        assert result.exit_code == 0
        assert "recommendations" in result.output
        assert "Why:" in result.output

    def test_recommend_json(self, mini_project):
        result = self.runner.invoke(
            app, ["recommend", str(mini_project), "--strategy", "cost", "--json"]
        )
        assert result.exit_code == 0
        rows = json.loads(result.output)
        assert rows and rows[0]["strategy"] == "cost"
        assert "explanation" in rows[0]

    def test_plan_json_has_fallbacks(self, mini_project):
        result = self.runner.invoke(
            app, ["plan", str(mini_project), "--strategy", "fidelity", "--json"]
        )
        assert result.exit_code == 0
        plan = json.loads(result.output)
        assert plan["strategy"] == "fidelity"
        assert "fallbacks" in plan and "explanation" in plan

    def test_plan_tight_budget_fails_cleanly(self, mini_project):
        result = self.runner.invoke(
            app, ["plan", str(mini_project), "--budget", "0.0001"]
        )
        assert result.exit_code == 2
        assert "budget" in result.output.lower()

    def test_health_lists_devices(self):
        result = self.runner.invoke(app, ["health", "--json"])
        assert result.exit_code == 0
        rows = json.loads(result.output)
        assert rows and "reliability" in rows[0] and "confidence" in rows[0]

    def test_unknown_strategy_rejected(self, mini_project):
        result = self.runner.invoke(app, ["recommend", str(mini_project), "-s", "wat"])
        assert result.exit_code != 0
