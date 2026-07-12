import json

import pytest
from qiskit import QuantumCircuit

from qontinuum.cli import app
from qontinuum.report.history import append_history
from qontinuum.report.schema import CheckResult, Status, SuiteResult
from qontinuum.report.schema import TestResult as TR


def record(statistic: float, status=Status.PASS) -> SuiteResult:
    return SuiteResult(
        tool_version="x", seed=1,
        tests=[TR(id="q_test_a.py::t", status=status, backend="aer", shots=1000,
                  circuit_hash="sha256:ab",
                  checks=[CheckResult(name="c", status=status, statistic=statistic,
                                      threshold=0.05)])],
    )


@pytest.fixture
def history_project(tmp_path):
    for stat, status in [(0.01, Status.PASS), (0.02, Status.PASS),
                         (0.09, Status.FAIL), (0.11, Status.FAIL)]:
        append_history(tmp_path, record(stat, status))
    return tmp_path


class TestHistoryGroup:
    def test_list_and_show(self, runner, history_project):
        result = runner.invoke(app, ["history", "list", "--path", str(history_project)])
        assert result.exit_code == 0
        show = runner.invoke(
            app, ["history", "show", "2", "--path", str(history_project), "--json"]
        )
        assert json.loads(show.output)["status"] == "fail"

    def test_stats(self, runner, history_project):
        result = runner.invoke(
            app, ["history", "stats", "--path", str(history_project), "--json"]
        )
        data = json.loads(result.output)
        assert data["runs"] == 4
        assert data["pass_rate"] == "50.0%"

    def test_export_csv(self, runner, history_project, tmp_path):
        out = history_project / "h.csv"
        result = runner.invoke(
            app, ["history", "export", "--path", str(history_project), "--out", str(out)]
        )
        assert result.exit_code == 0
        assert out.read_text().startswith("run,when,status")

    def test_compare_flags_regression(self, runner, history_project):
        result = runner.invoke(
            app, ["history", "compare", "0", "3", "--path", str(history_project), "--json"]
        )
        rows = json.loads(result.output)
        assert rows[0]["delta"] == pytest.approx(0.10)

    def test_bisect_finds_first_bad_run(self, runner, history_project):
        result = runner.invoke(
            app, ["history", "bisect", "q_test_a.py::t", "--path", str(history_project),
                  "--json"]
        )
        assert result.exit_code == 1  # found a regression
        data = json.loads(result.output)
        assert data["last_good_run"] == 1
        assert data["first_bad_run"] == 2

    def test_bisect_never_failed(self, runner, tmp_path):
        append_history(tmp_path, record(0.01))
        result = runner.invoke(
            app, ["history", "bisect", "q_test_a.py::t", "--path", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "never failed" in result.output

    def test_prune(self, runner, history_project):
        result = runner.invoke(
            app, ["history", "prune", "--path", str(history_project), "--keep", "2"]
        )
        assert "pruned 2" in result.output


class TestNoiseScaling:
    def test_profile_scales_and_caps(self):
        from qontinuum.noise.scaling import NoiseProfile

        p = NoiseProfile(0.001, 0.01, 0.02)
        doubled = p.scaled(2)
        assert doubled.error_2q == pytest.approx(0.02)
        capped = p.scaled(1e6)
        assert capped.error_2q <= 0.9375 and capped.error_readout <= 0.5

    def test_zero_scale_is_ideal(self):
        from qiskit import transpile

        from qontinuum.assertions.stats import normalize_counts
        from qontinuum.noise.scaling import NoiseProfile, simulator_for

        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cx(0, 1)
        qc.measure_all()
        backend = simulator_for(NoiseProfile(0, 0, 0))
        counts = normalize_counts(
            backend.run(transpile(qc, backend), shots=1000, seed_simulator=1)
            .result().get_counts()
        )
        assert set(counts) <= {"00", "11"}

    def test_more_noise_more_leakage(self):
        from qiskit import transpile

        from qontinuum.assertions.stats import normalize_counts
        from qontinuum.noise.scaling import NoiseProfile, simulator_for

        def leakage(profile):
            qc = QuantumCircuit(2)
            qc.h(0)
            qc.cx(0, 1)
            qc.measure_all()
            backend = simulator_for(profile)
            counts = normalize_counts(
                backend.run(transpile(qc, backend), shots=4000, seed_simulator=3)
                .result().get_counts()
            )
            return counts.get("01", 0) + counts.get("10", 0)

        assert leakage(NoiseProfile(0.001, 0.01, 0.01)) < leakage(NoiseProfile(0.01, 0.1, 0.1))

    def test_inject_cli(self, runner, mini_project):
        result = runner.invoke(
            app, ["noise", "inject", "bell", "--path", str(mini_project),
                  "--error-2q", "0.5", "--readout", "0.3", "--json"]
        )
        assert result.exit_code == 1  # that much noise must break a 0.06 TVD check
        assert json.loads(result.output)["status"] == "FAIL"


class TestBench:
    def test_mirror_ideal_is_perfect(self):
        from qontinuum.bench.core import mirror_survival

        qc = QuantumCircuit(2)
        qc.h(0)
        qc.cx(0, 1)
        assert mirror_survival(qc, backend_spec="aer", shots=500, seed=1) == 1.0

    def test_rb_ideal_no_decay(self):
        from qontinuum.bench.core import rb_lite

        result = rb_lite(qubits=1, lengths=(1, 4, 8), trials=1, shots=300,
                         backend_spec="aer", seed=2)
        assert result.error_per_layer < 0.01

    def test_qv_ideal_passes_widths(self):
        from qontinuum.bench.core import qv_estimate

        result = qv_estimate(max_qubits=3, trials=4, shots=300, backend_spec="aer", seed=3)
        assert result.quantum_volume_estimate >= 4

    def test_bench_mirror_cli(self, runner):
        result = runner.invoke(
            app, ["bench", "mirror", "--qubits", "2", "--depth", "3", "--json"]
        )
        assert result.exit_code == 0
        assert json.loads(result.output)["mirror_survival"] == 1.0
