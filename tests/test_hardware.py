import textwrap

import pytest
from typer.testing import CliRunner

from qontinuum.cli import app
from qontinuum.hardware import (
    HardwareError,
    SpendGuardError,
    estimate_hardware_cost,
    resolve_adapter,
    run_suite_on_hardware,
)
from qontinuum.report.schema import Status

SUITE = """
from qiskit import QuantumCircuit
from qontinuum import qtest, assert_distribution

@qtest(shots=1000)
def bell():
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc

@bell.check
def entangled(result):
    assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.1)
"""


class FakeAdapter:
    """Pretends to be a perfect Rigetti Cepheus."""

    target = "fake:rigetti"
    catalog_device = ("braket", "rigetti_cepheus")

    def __init__(self):
        self.submitted = []

    def submit(self, circuit, shots):
        self.submitted.append((circuit, shots))
        return {"00": shots // 2, "11": shots - shots // 2}


class ExplodingAdapter(FakeAdapter):
    def submit(self, circuit, shots):
        raise RuntimeError("queue on fire")


def suite_dir(tmp_path):
    (tmp_path / "q_test_hw.py").write_text(textwrap.dedent(SUITE))
    return tmp_path


class TestSpendGuard:
    def test_estimate_matches_catalog(self, tmp_path):
        from qontinuum.runner.discovery import discover

        items = discover(suite_dir(tmp_path))
        pairs = [(i.test.build(), i.test.shots) for i in items]
        # Rigetti: 0.30 + 1000 * 0.000425 = 0.725
        assert estimate_hardware_cost(pairs, ("braket", "rigetti_cepheus")) == pytest.approx(
            0.725
        )

    def test_default_budget_refuses_everything(self, tmp_path):
        with pytest.raises(SpendGuardError, match="nothing was submitted"):
            run_suite_on_hardware(suite_dir(tmp_path), FakeAdapter(), max_cost=0.0)

    def test_guard_blocks_before_any_submission(self, tmp_path):
        adapter = FakeAdapter()
        with pytest.raises(SpendGuardError):
            run_suite_on_hardware(suite_dir(tmp_path), adapter, max_cost=0.5)
        assert adapter.submitted == []

    def test_unpriceable_device_refused(self, tmp_path):
        adapter = FakeAdapter()
        adapter.catalog_device = ("azure", "quantinuum_h2")  # HQC, no dollar rate
        with pytest.raises(SpendGuardError, match="dollar rate"):
            run_suite_on_hardware(suite_dir(tmp_path), adapter, max_cost=1e9)

    def test_dry_run_submits_nothing(self, tmp_path):
        adapter = FakeAdapter()
        suite, estimated = run_suite_on_hardware(
            suite_dir(tmp_path), adapter, max_cost=5.0, dry_run=True
        )
        assert adapter.submitted == []
        assert estimated == pytest.approx(0.725)
        assert suite.tests == []


class TestHardwareRun:
    def test_full_run_evaluates_checks(self, tmp_path):
        adapter = FakeAdapter()
        suite, _ = run_suite_on_hardware(suite_dir(tmp_path), adapter, max_cost=5.0)
        assert len(adapter.submitted) == 1
        (test,) = suite.tests
        assert test.status is Status.PASS
        assert test.backend == "hw:fake:rigetti"
        assert test.checks[0].statistic is not None  # captured even on pass
        assert sum(test.counts.values()) == 1000

    def test_submission_failure_is_error_not_crash(self, tmp_path):
        suite, _ = run_suite_on_hardware(suite_dir(tmp_path), ExplodingAdapter(), max_cost=5.0)
        (test,) = suite.tests
        assert test.status is Status.ERROR
        assert "queue on fire" in test.error


class TestResolveAdapter:
    def test_bad_spec_rejected(self):
        with pytest.raises(HardwareError, match="expected"):
            resolve_adapter("ibm_brisbane")  # missing provider prefix

    def test_unknown_provider_rejected(self):
        with pytest.raises(HardwareError, match="unknown hardware provider"):
            resolve_adapter("dwave:advantage")

    def test_unknown_braket_device_lists_options(self):
        with pytest.raises(HardwareError, match="available"):
            resolve_adapter("braket:not_a_device")


class TestRunCli:
    def test_requires_on(self, tmp_path):
        result = CliRunner().invoke(app, ["run", str(suite_dir(tmp_path))])
        assert result.exit_code == 2
        assert "--on is required" in result.output

    def test_spend_guard_message_reaches_user(self, tmp_path):
        # braket adapter for an unknown device fails fast without SDKs.
        result = CliRunner().invoke(
            app, ["run", str(suite_dir(tmp_path)), "--on", "braket:not_real"]
        )
        assert result.exit_code == 2
        assert "hardware error" in result.output
