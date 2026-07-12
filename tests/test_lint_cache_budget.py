import textwrap

import pytest

from qontinuum import budget, cache, config
from qontinuum.cli import app
from qontinuum.lint import lint_path

BAD_SUITE = """
from qiskit import QuantumCircuit
from qontinuum import qtest, assert_distribution

@qtest(shots=50)  # Q009: trivially low
def unsound():
    qc = QuantumCircuit(3)  # Q003: qubit 2 idle
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc

@unsound.check
def too_tight(result):
    assert_distribution(result, {"000": 0.5, "011": 0.5}, tvd_threshold=0.001)  # Q001

@qtest(shots=1000, snapshot=True)  # Q006: no baseline
def unbaselined_snapshot():
    qc = QuantumCircuit(1)
    qc.h(0)
    qc.measure_all()
    return qc

@qtest(shots=1000)
def never_measured():
    return QuantumCircuit(2)  # Q002

@qtest(shots=1000, backend="ibm:brisbane@live")  # Q008
def live_dependency():
    qc = QuantumCircuit(1)
    qc.h(0)
    qc.measure_all()
    return qc
"""


class TestLintRules:
    @pytest.fixture
    def findings(self, tmp_path):
        (tmp_path / "q_test_bad.py").write_text(textwrap.dedent(BAD_SUITE))
        return {f.code for f in lint_path(tmp_path)}

    def test_expected_rules_fire(self, findings):
        assert {"Q001", "Q002", "Q003", "Q006", "Q008", "Q009"} <= findings

    def test_clean_suite_has_no_findings(self, mini_project):
        assert lint_path(mini_project) == []

    def test_select_filters(self, tmp_path):
        (tmp_path / "q_test_bad.py").write_text(textwrap.dedent(BAD_SUITE))
        only = lint_path(tmp_path, select={"Q003"})
        assert {f.code for f in only} == {"Q003"}

    def test_ignore_filters(self, tmp_path):
        (tmp_path / "q_test_bad.py").write_text(textwrap.dedent(BAD_SUITE))
        rest = lint_path(tmp_path, ignore={"Q001", "Q002", "Q003", "Q006", "Q008", "Q009"})
        assert {f.code for f in rest} == set()

    def test_unknown_code_raises(self, tmp_path):
        (tmp_path / "q_test_bad.py").write_text(textwrap.dedent(BAD_SUITE))
        with pytest.raises(ValueError, match="unknown rule"):
            lint_path(tmp_path, select={"Q999"})

    def test_cli_exit_codes(self, runner, tmp_path, mini_project):
        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        (bad_dir / "q_test_bad.py").write_text(textwrap.dedent(BAD_SUITE))
        assert runner.invoke(app, ["lint", "check", str(bad_dir)]).exit_code == 1
        clean_dir = mini_project / "clean"
        clean_dir.mkdir()
        (mini_project / "q_test_bell.py").rename(clean_dir / "q_test_bell.py")
        assert runner.invoke(app, ["lint", "check", str(clean_dir)]).exit_code == 0

    def test_cli_rules_and_explain(self, runner):
        assert "Q001" in runner.invoke(app, ["lint", "rules"]).output
        result = runner.invoke(app, ["lint", "explain", "Q001"])
        assert "sampling floor" in result.output.lower()
        assert runner.invoke(app, ["lint", "explain", "Q999"]).exit_code == 2


class TestCache:
    def test_roundtrip(self, tmp_path):
        key = cache.cache_key("sha256:abc", "aer", 100, 7)
        assert cache.get(tmp_path, key) is None
        cache.put(tmp_path, key, {"00": 60, "11": 40}, meta={"test": "t"})
        assert cache.get(tmp_path, key) == {"00": 60, "11": 40}
        assert cache.entries(tmp_path)[0]["shots"] == 100

    def test_corrupt_entry_self_heals(self, tmp_path):
        key = cache.cache_key("h", "aer", 1, 1)
        cache.put(tmp_path, key, {"0": 1})
        path = tmp_path / cache.CACHE_DIR / f"{key}.json"
        path.write_text("{broken")
        assert cache.get(tmp_path, key) is None
        assert not path.exists()

    def test_clear(self, tmp_path):
        cache.put(tmp_path, "k1", {"0": 1})
        cache.put(tmp_path, "k2", {"0": 1})
        assert cache.clear(tmp_path) == 2
        assert cache.entries(tmp_path) == []

    def test_cached_run_hits_cache(self, runner, mini_project):
        first = runner.invoke(app, ["test", str(mini_project), "--seed", "3", "--cached"])
        assert first.exit_code == 0
        assert len(cache.entries(mini_project)) == 1
        second = runner.invoke(
            app, ["test", str(mini_project), "--seed", "3", "--cached", "--json",
                  str(mini_project / "out.json")]
        )
        assert second.exit_code == 0
        import json

        suite = json.loads((mini_project / "out.json").read_text())
        assert suite["tests"][0]["cached"] is True

    def test_cached_without_seed_rejected(self, runner, mini_project):
        assert runner.invoke(app, ["test", str(mini_project), "--cached"]).exit_code == 2


class TestBudget:
    def test_ledger_and_status(self, tmp_path):
        budget.record_spend(tmp_path, usd=3.5, target="t", tests=2)
        budget.record_spend(tmp_path, usd=1.5, target="t", tests=1)
        assert budget.spent(tmp_path) == 5.0
        assert budget.status(tmp_path)["runs_recorded"] == 2

    def test_monthly_cap_enforced(self, tmp_path):
        config.set_value(tmp_path, "budget.monthly_usd", "10")
        budget.record_spend(tmp_path, usd=8, target="t", tests=1)
        budget.check_budget(tmp_path, 1.0)  # fits
        with pytest.raises(budget.BudgetExceededError, match="monthly"):
            budget.check_budget(tmp_path, 3.0)

    def test_total_cap_enforced(self, tmp_path):
        config.set_value(tmp_path, "budget.total_usd", "5")
        budget.record_spend(tmp_path, usd=4.99, target="t", tests=1)
        with pytest.raises(budget.BudgetExceededError, match="total"):
            budget.check_budget(tmp_path, 0.02)

    def test_no_caps_no_guard(self, tmp_path):
        budget.check_budget(tmp_path, 1e9)  # no config: unlimited

    def test_hardware_run_blocked_by_budget(self, mini_project):
        from qontinuum.hardware import SpendGuardError, run_suite_on_hardware

        class FakeAdapter:
            target = "fake:rigetti"
            catalog_device = ("braket", "rigetti_cepheus")

            def submit(self, circuit, shots):  # pragma: no cover - guard blocks first
                raise AssertionError("must not submit")

        config.set_value(mini_project, "budget.total_usd", "0.5")
        with pytest.raises(SpendGuardError, match="total budget"):
            run_suite_on_hardware(mini_project, FakeAdapter(), max_cost=100.0)

    def test_cli_budget_flow(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert runner.invoke(app, ["budget", "set", "25", "--monthly"]).exit_code == 0
        result = runner.invoke(app, ["budget", "status", "--json"])
        import json

        assert json.loads(result.output)["monthly_cap_usd"] == 25
