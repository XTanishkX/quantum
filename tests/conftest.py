import textwrap

import pytest
from typer.testing import CliRunner

PASSING_BELL = """
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

QASM_BELL = """
OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
c = measure q;
"""


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def mini_project(tmp_path):
    """A tmp project with one passing bell test and a QASM file."""
    (tmp_path / "q_test_bell.py").write_text(textwrap.dedent(PASSING_BELL))
    (tmp_path / "bell.qasm").write_text(QASM_BELL)
    return tmp_path
