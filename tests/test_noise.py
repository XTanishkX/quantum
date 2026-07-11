import textwrap

import pytest

pytest.importorskip("qiskit_ibm_runtime")

from qontinuum.assertions import stats
from qontinuum.noise import NoiseSourceError, noisy_simulator
from qontinuum.report.schema import Status
from qontinuum.runner.backends import execute
from qontinuum.runner.engine import run_suite


def bell():
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


class TestNoisySimulator:
    def test_resolves_bundled_device_names_flexibly(self):
        for name in ["manila", "fake_manila", "ibm_manila"]:
            assert noisy_simulator(name) is not None

    def test_unknown_device_lists_available(self):
        with pytest.raises(NoiseSourceError, match="available devices"):
            noisy_simulator("not_a_device_xyz")

    def test_unknown_mode_rejected(self):
        with pytest.raises(NoiseSourceError, match="@live"):
            noisy_simulator("manila@yesterday")


class TestNoisyExecution:
    def test_noise_degrades_bell_state_realistically(self):
        ideal = execute(bell(), shots=8000, backend_spec="aer", seed=7)
        noisy = execute(bell(), shots=8000, backend_spec="ibm:manila", seed=7)

        expected = {"00": 0.5, "11": 0.5}
        assert stats.tvd(ideal.counts, expected) < 0.02
        noisy_tvd = stats.tvd(noisy.counts, expected)
        # Real calibration noise must show up, but a Bell pair on a real
        # device still lands well under TVD 0.2.
        assert 0.005 < noisy_tvd < 0.2

    def test_noise_produces_odd_parity_leakage(self):
        noisy = execute(bell(), shots=8000, backend_spec="ibm:manila", seed=7)
        leakage = noisy.counts.get("01", 0) + noisy.counts.get("10", 0)
        assert leakage > 0


def test_suite_runs_against_noisy_backend(tmp_path):
    (tmp_path / "q_test_noisy.py").write_text(
        textwrap.dedent(
            """
            from qiskit import QuantumCircuit
            from qontinuum import qtest, assert_distribution

            @qtest(shots=4000, backend="ibm:manila")
            def bell_under_noise():
                qc = QuantumCircuit(2)
                qc.h(0)
                qc.cx(0, 1)
                qc.measure_all()
                return qc

            @bell_under_noise.check
            def close_to_ideal_despite_noise(result):
                assert_distribution(
                    result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.2
                )
            """
        )
    )
    suite = run_suite(tmp_path, seed=3)
    (test,) = suite.tests
    assert test.status is Status.PASS
    assert test.backend == "ibm:manila"
