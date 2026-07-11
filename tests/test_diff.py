from qiskit import QuantumCircuit
from qiskit.circuit import ClassicalRegister, QuantumRegister
from typer.testing import CliRunner

from qontinuum.circuits import diff_circuits
from qontinuum.cli import app


def bell(cx_direction=(0, 1)) -> QuantumCircuit:
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(*cx_direction)
    qc.measure([0, 1], [0, 1])
    return qc


class TestDiffCircuits:
    def test_identical_circuits(self):
        d = diff_circuits(bell(), bell())
        assert d.identical
        assert d.n_added == d.n_removed == 0
        assert all(line.tag == " " for line in d.lines)

    def test_renamed_registers_are_identical(self):
        a = QuantumCircuit(QuantumRegister(2, "alpha"), ClassicalRegister(2, "ca"))
        a.h(0)
        a.measure([0, 1], [0, 1])
        b = QuantumCircuit(QuantumRegister(2, "beta"), ClassicalRegister(2, "cb"))
        b.h(0)
        b.measure([0, 1], [0, 1])
        assert diff_circuits(a, b).identical

    def test_gate_change_shows_minus_and_plus(self):
        d = diff_circuits(bell((0, 1)), bell((1, 0)))
        assert not d.identical
        assert d.n_removed == 1
        assert d.n_added == 1
        removed = next(line for line in d.lines if line.tag == "-")
        added = next(line for line in d.lines if line.tag == "+")
        assert "cx q[0, 1]" in removed.text
        assert "cx q[1, 0]" in added.text

    def test_added_gate(self):
        b = bell()
        b.data.insert(1, b.data[0])  # duplicate the h
        d = diff_circuits(bell(), b)
        assert d.n_added == 1
        assert d.n_removed == 0

    def test_qubit_count_change_reported(self):
        wide = QuantumCircuit(3, 3)
        wide.h(0)
        wide.measure([0, 1, 2], [0, 1, 2])
        d = diff_circuits(bell(), wide)
        texts = [line.text for line in d.lines if line.tag in "-+"]
        assert "qubits: 2" in texts
        assert "qubits: 3" in texts

    def test_parameterized_gate_renders_value(self):
        a = QuantumCircuit(1, 1)
        a.rz(0.5, 0)
        a.measure(0, 0)
        b = QuantumCircuit(1, 1)
        b.rz(0.75, 0)
        b.measure(0, 0)
        d = diff_circuits(a, b)
        assert any("rz(0.5)" in line.text for line in d.lines if line.tag == "-")
        assert any("rz(0.75)" in line.text for line in d.lines if line.tag == "+")


QASM_A = """
OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
c = measure q;
"""

QASM_B = QASM_A.replace("cx q[0], q[1];", "cx q[1], q[0];")


class TestCliCommands:
    def test_hash_command(self, tmp_path):
        f = tmp_path / "a.qasm"
        f.write_text(QASM_A)
        result = CliRunner().invoke(app, ["hash", str(f)])
        assert result.exit_code == 0
        assert "sha256:" in result.output

    def test_diff_identical_exits_zero(self, tmp_path):
        f1, f2 = tmp_path / "a.qasm", tmp_path / "b.qasm"
        f1.write_text(QASM_A)
        f2.write_text(QASM_A.replace("q;", "q;  "))  # formatting only
        result = CliRunner().invoke(app, ["diff", str(f1), str(f2)])
        assert result.exit_code == 0
        assert "identical" in result.output

    def test_diff_changed_exits_one_and_shows_ops(self, tmp_path):
        f1, f2 = tmp_path / "a.qasm", tmp_path / "b.qasm"
        f1.write_text(QASM_A)
        f2.write_text(QASM_B)
        result = CliRunner().invoke(app, ["diff", str(f1), str(f2)])
        assert result.exit_code == 1
        assert "1 ops added, 1 removed" in result.output
