"""Planning completion (queue/confidence/risk) and the engineering report."""

from __future__ import annotations

from qiskit import QuantumCircuit
from typer.testing import CliRunner

from qontinuum.cli import app
from qontinuum.cost import estimate_suite, load_catalog, profile_circuit
from qontinuum.intelligence import Strategy, assess_health, build_plan, recommend
from qontinuum.intelligence.models import Recommendation
from qontinuum.intelligence.planning import risk_level
from qontinuum.report.engineering import render_engineering_report
from qontinuum.telemetry.schema import CommunityAggregate


def _bell():
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


def _recs(strategy=Strategy.BALANCED, community=None):
    qc = _bell()
    catalog = load_catalog()
    profiles = [profile_circuit(qc)]
    estimates = estimate_suite([(qc, 2000)])
    health = assess_health(catalog, community=community)
    return recommend(profiles, [2000], estimates, catalog, strategy=strategy, health=health)


class TestPlanningCompletion:
    def test_plan_has_confidence_and_risk(self):
        plan = build_plan(_recs(), strategy=Strategy.BALANCED, workload="demo")
        assert 0.0 <= plan.confidence <= 1.0
        assert plan.risk_level in {"low", "medium", "high"}

    def test_queue_comes_from_community(self):
        agg = CommunityAggregate.model_validate(
            {"schema_version": 1, "generated_at": "x",
             "devices": {"heron_payg": {"samples": 80, "success_rate": 0.9,
                                        "avg_queue_s": 42.0}}})
        recs = _recs(community=agg)
        heron = next((r for r in recs if r.device == "heron_payg"), None)
        assert heron is not None and heron.queue_s == 42.0

    def test_risk_level_thresholds(self):
        def rec(success, risks):
            return Recommendation(strategy="x", provider="p", device="d", display="D",
                                  success_prob=success, risks=risks)
        assert risk_level(rec(0.99, [])) == "low"
        assert risk_level(rec(0.7, [])) == "medium"
        assert risk_level(rec(0.4, [])) == "high"
        assert risk_level(rec(0.99, ["a", "b", "c"])) == "high"
        blocked = rec(None, [])
        blocked.feasible = False
        assert risk_level(blocked) == "blocked"


class TestEngineeringReport:
    def _render(self, recs, plan):
        return render_engineering_report(
            workload="proj", strategy="balanced", recommendations=recs, plan=plan,
            healths=assess_health(load_catalog()),
            estimates=estimate_suite([(_bell(), 2000)]),
            analytics={"runs": 3, "suite_pass_rate": "67.0%", "hardware_runs": 1,
                       "hardware_success_rate": "100.0%", "estimated_spend_usd": 1.2},
            tool_version="0.5.0",
        )

    def test_report_has_all_sections(self):
        recs = _recs()
        plan = build_plan(recs, strategy=Strategy.BALANCED, workload="proj")
        md = self._render(recs, plan)
        for heading in ("# ⚛️ Qontinuum engineering report", "## Execution plan",
                        "## Ranked recommendations", "## Provider analysis",
                        "## Cost analysis", "## Historical context"):
            assert heading in md
        assert "risk:" in md and "confidence:" in md

    def test_report_handles_no_plan(self):
        md = self._render(_recs(), None)
        assert "No feasible device" in md

    def test_report_history_absent(self):
        recs = _recs()
        plan = build_plan(recs, strategy=Strategy.BALANCED, workload="proj")
        md = render_engineering_report(
            workload="proj", strategy="balanced", recommendations=recs, plan=plan,
            healths=assess_health(load_catalog()), estimates=[], analytics={"runs": 0})
        assert "No local run history" in md


class TestEngineeringReportCli:
    def test_cli_renders(self, mini_project):
        result = CliRunner().invoke(
            app, ["report", "engineering", "--path", str(mini_project)])
        assert result.exit_code == 0
        assert "Qontinuum engineering report" in result.output
        assert "Execution plan" in result.output

    def test_cli_unknown_strategy(self, mini_project):
        result = CliRunner().invoke(
            app, ["report", "engineering", "--path", str(mini_project), "-s", "nope"])
        assert result.exit_code == 2
