import textwrap

import pytest

from qontinuum.report.schema import Status
from qontinuum.runner.engine import run_suite
from qontinuum.runner.qtest import QuantumTest, qtest

PASSING_SUITE = """
from qiskit import QuantumCircuit
from qontinuum import qtest, assert_distribution, assert_probability

@qtest(shots=4000)
def bell_pair():
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc

@bell_pair.check
def is_maximally_entangled(result):
    assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.05)

@bell_pair.check
def no_odd_parity(result):
    assert_probability(result, "01", max_p=0.01)
    assert_probability(result, "10", max_p=0.01)
"""

FAILING_SUITE = """
from qiskit import QuantumCircuit
from qontinuum import qtest, assert_distribution

@qtest(shots=4000)
def broken_bell():
    qc = QuantumCircuit(2)
    qc.h(0)  # missing the cx: not entangled
    qc.measure_all()
    return qc

@broken_bell.check
def is_maximally_entangled(result):
    assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.05)
"""

ERROR_SUITE = """
from qiskit import QuantumCircuit
from qontinuum import qtest

@qtest
def no_measurements():
    return QuantumCircuit(2)
"""

SNAPSHOT_SUITE = """
from qiskit import QuantumCircuit
from qontinuum import qtest

@qtest(shots=2000, snapshot=True)
def ghz():
    qc = QuantumCircuit(3)
    qc.h(0)
    qc.cx(0, 1)
    qc.cx(1, 2)
    qc.measure_all()
    return qc
"""


def write_suite(tmp_path, source, name="q_test_suite.py"):
    (tmp_path / name).write_text(textwrap.dedent(source))
    return tmp_path


class TestQtestDecorator:
    def test_bare_decorator(self):
        @qtest
        def t():  # pragma: no cover - factory body unused
            pass

        assert isinstance(t, QuantumTest)
        assert t.name == "t"
        assert t.shots == 1024

    def test_configured_decorator(self):
        @qtest(shots=99, backend="aer", name="renamed")
        def t():  # pragma: no cover
            pass

        assert t.shots == 99
        assert t.name == "renamed"

    def test_check_registration(self):
        @qtest
        def t():  # pragma: no cover
            pass

        @t.check
        def one(result):  # pragma: no cover
            pass

        @t.check
        def two(result):  # pragma: no cover
            pass

        assert [c.__name__ for c in t.checks] == ["one", "two"]


class TestRunSuite:
    def test_passing_suite(self, tmp_path):
        suite = run_suite(write_suite(tmp_path, PASSING_SUITE), seed=7)
        assert suite.status is Status.PASS
        (test,) = suite.tests
        assert test.id.endswith("::bell_pair")
        assert len(test.checks) == 2
        assert test.circuit_hash.startswith("sha256:")
        assert sum(test.counts.values()) == 4000

    def test_failing_suite(self, tmp_path):
        suite = run_suite(write_suite(tmp_path, FAILING_SUITE), seed=7)
        assert suite.status is Status.FAIL
        (check,) = suite.tests[0].checks
        assert check.status is Status.FAIL
        assert "TVD" in check.message

    def test_error_suite_missing_measurements(self, tmp_path):
        suite = run_suite(write_suite(tmp_path, ERROR_SUITE), seed=7)
        assert suite.status is Status.ERROR
        assert "measure" in suite.tests[0].error

    def test_seed_makes_runs_reproducible(self, tmp_path):
        root = write_suite(tmp_path, PASSING_SUITE)
        a = run_suite(root, seed=11)
        b = run_suite(root, seed=11)
        assert a.tests[0].counts == b.tests[0].counts

    def test_equivalent_refactor_keeps_hash(self, tmp_path):
        refactored = PASSING_SUITE.replace(
            "qc = QuantumCircuit(2)", "qc = QuantumCircuit(2)\n    pass"
        )
        a = run_suite(write_suite(tmp_path, PASSING_SUITE), seed=3)
        b = run_suite(write_suite(tmp_path, refactored, name="q_test_refactored.py"), seed=3)
        hashes = {t.circuit_hash for t in [*a.tests, *b.tests]}
        assert len(hashes) == 1


class TestSnapshots:
    def test_missing_snapshot_is_error_with_hint(self, tmp_path):
        suite = run_suite(write_suite(tmp_path, SNAPSHOT_SUITE), seed=5)
        (check,) = suite.tests[0].checks
        assert check.status is Status.ERROR
        assert "qont snapshot update" in check.message

    def test_update_then_check_passes(self, tmp_path):
        root = write_suite(tmp_path, SNAPSHOT_SUITE)
        recorded = run_suite(root, seed=5, update_snapshots=True)
        assert recorded.status is Status.PASS
        assert (root / ".qontinuum" / "snapshots.json").is_file()
        replay = run_suite(root, seed=99)  # different sample, same distribution
        assert replay.status is Status.PASS

    def test_changed_circuit_marks_snapshot_stale(self, tmp_path):
        root = write_suite(tmp_path, SNAPSHOT_SUITE)
        run_suite(root, seed=5, update_snapshots=True)
        changed = SNAPSHOT_SUITE.replace("qc.cx(1, 2)", "qc.cx(0, 2)\n    qc.x(2)")
        write_suite(root, changed)
        suite = run_suite(root, seed=5)
        (check,) = suite.tests[0].checks
        assert check.status is Status.FAIL
        assert "circuit changed" in check.message

    def test_distribution_drift_fails_snapshot(self, tmp_path):
        root = write_suite(tmp_path, SNAPSHOT_SUITE)
        run_suite(root, seed=5, update_snapshots=True)
        # Tamper with the recorded baseline to simulate drift with an
        # unchanged circuit (e.g. a transpiler or noise-model change).
        import json

        snap_file = root / ".qontinuum" / "snapshots.json"
        data = json.loads(snap_file.read_text())
        (entry,) = data["snapshots"].values()
        entry["counts"] = {"000": 1500, "111": 300, "010": 200}
        snap_file.write_text(json.dumps(data))
        suite = run_suite(root, seed=5)
        (check,) = suite.tests[0].checks
        assert check.status is Status.FAIL
        assert "drifted" in check.message


def test_discovery_skips_hidden_dirs(tmp_path):
    write_suite(tmp_path, PASSING_SUITE)
    hidden = tmp_path / ".venv" / "lib"
    hidden.mkdir(parents=True)
    (hidden / "q_test_should_skip.py").write_text("raise RuntimeError('imported!')")
    suite = run_suite(tmp_path, seed=1)
    assert len(suite.tests) == 1


def test_broken_test_file_reports_discovery_error(tmp_path):
    (tmp_path / "q_test_broken.py").write_text("import nonexistent_module_xyz")
    with pytest.raises(Exception, match="failed to import"):
        run_suite(tmp_path)
