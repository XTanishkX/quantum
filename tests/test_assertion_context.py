import textwrap

import pytest

from qontinuum.assertions import assert_distribution, assert_fidelity
from qontinuum.assertions.context import capture_assertions, record
from qontinuum.report.schema import Status
from qontinuum.runner.engine import run_suite

BELL = {"00": 0.5, "11": 0.5}


class TestCaptureContext:
    def test_passing_assertions_record_statistics(self):
        with capture_assertions() as events:
            assert_distribution({"00": 2000, "11": 2000}, BELL, tvd_threshold=0.05)
            assert_fidelity({"00": 2000, "11": 2000}, BELL, min_fidelity=0.9)
        kinds = [e.kind for e in events]
        assert kinds == ["tvd", "fidelity"]
        assert events[0].statistic == pytest.approx(0.0)
        assert events[0].threshold == 0.05
        assert events[1].statistic == pytest.approx(1.0)

    def test_record_is_noop_outside_context(self):
        record("tvd", 0.1, 0.05)  # must not raise or leak anywhere

    def test_contexts_do_not_leak(self):
        with capture_assertions() as outer:
            record("a", 1.0)
            with capture_assertions() as inner:
                record("b", 2.0)
        assert [e.kind for e in outer] == ["a"]
        assert [e.kind for e in inner] == ["b"]


def test_passing_suite_carries_statistics(tmp_path):
    (tmp_path / "q_test_s.py").write_text(
        textwrap.dedent(
            """
            from qiskit import QuantumCircuit
            from qontinuum import qtest, assert_distribution

            @qtest(shots=2000)
            def bell():
                qc = QuantumCircuit(2)
                qc.h(0)
                qc.cx(0, 1)
                qc.measure_all()
                return qc

            @bell.check
            def entangled(result):
                assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.06)
            """
        )
    )
    suite = run_suite(tmp_path, seed=4)
    (check,) = suite.tests[0].checks
    assert check.status is Status.PASS
    assert check.statistic is not None
    assert 0 <= check.statistic < 0.06
    assert check.threshold == 0.06
