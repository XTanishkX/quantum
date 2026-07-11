import math

import pytest
from qiskit import QuantumCircuit
from qiskit.circuit import ClassicalRegister, QuantumRegister

from qontinuum.circuits import CircuitLoadError, circuit_hash, load_circuit

QASM3_BELL = """
OPENQASM 3.0;
include "stdgates.inc";
qubit[2] q;
bit[2] c;
h q[0];
cx q[0], q[1];
c = measure q;
"""

QASM2_BELL = """
OPENQASM 2.0;
include "qelib1.inc";
qreg q[2];
creg c[2];
h q[0];
cx q[0], q[1];
measure q -> c;
"""


def bell() -> QuantumCircuit:
    qc = QuantumCircuit(2, 2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure([0, 1], [0, 1])
    return qc


class TestLoadCircuit:
    def test_passthrough_quantum_circuit(self):
        qc = bell()
        assert load_circuit(qc) is qc

    def test_loads_qasm3_string(self):
        qc = load_circuit(QASM3_BELL)
        assert qc.num_qubits == 2

    def test_loads_qasm2_string(self):
        qc = load_circuit(QASM2_BELL)
        assert qc.num_qubits == 2

    def test_loads_qasm_file(self, tmp_path):
        f = tmp_path / "bell.qasm"
        f.write_text(QASM3_BELL)
        assert load_circuit(f).num_qubits == 2
        assert load_circuit(str(f)).num_qubits == 2

    def test_rejects_garbage(self):
        with pytest.raises(CircuitLoadError):
            load_circuit("not a circuit at all")

    def test_rejects_bad_qasm(self):
        with pytest.raises(CircuitLoadError):
            load_circuit("OPENQASM 3.0; this is broken;")


class TestCircuitHash:
    def test_deterministic(self):
        assert circuit_hash(bell()) == circuit_hash(bell())
        assert circuit_hash(bell()).startswith("sha256:")

    def test_register_names_do_not_matter(self):
        a = QuantumCircuit(QuantumRegister(2, "alpha"), ClassicalRegister(2, "m"))
        a.h(0)
        a.cx(0, 1)
        a.measure([0, 1], [0, 1])
        b = QuantumCircuit(QuantumRegister(2, "beta"), ClassicalRegister(2, "bits"))
        b.h(0)
        b.cx(0, 1)
        b.measure([0, 1], [0, 1])
        assert circuit_hash(a) == circuit_hash(b)

    def test_circuit_name_and_metadata_do_not_matter(self):
        a = bell()
        a.name = "one"
        a.metadata = {"run": 1}
        b = bell()
        b.name = "two"
        b.metadata = {"run": 2}
        assert circuit_hash(a) == circuit_hash(b)

    def test_qasm_roundtrip_matches_native_construction(self):
        assert circuit_hash(load_circuit(QASM3_BELL)) == circuit_hash(bell())

    def test_different_ops_hash_differently(self):
        a = bell()
        b = QuantumCircuit(2, 2)
        b.h(0)
        b.cx(1, 0)  # flipped control/target
        b.measure([0, 1], [0, 1])
        assert circuit_hash(a) != circuit_hash(b)

    def test_param_precision_noise_ignored(self):
        a = QuantumCircuit(1)
        a.rz(math.pi / 3, 0)
        b = QuantumCircuit(1)
        b.rz(math.pi / 3 + 1e-15, 0)
        assert circuit_hash(a) == circuit_hash(b)

    def test_materially_different_params_differ(self):
        a = QuantumCircuit(1)
        a.rz(0.5, 0)
        b = QuantumCircuit(1)
        b.rz(0.6, 0)
        assert circuit_hash(a) != circuit_hash(b)

    def test_control_flow_blocks_hashed(self):
        a = QuantumCircuit(1, 1)
        a.h(0)
        a.measure(0, 0)
        with a.if_test((a.clbits[0], 1)):
            a.x(0)

        b = QuantumCircuit(1, 1)
        b.h(0)
        b.measure(0, 0)
        with b.if_test((b.clbits[0], 1)):
            b.z(0)  # different body

        assert circuit_hash(a) != circuit_hash(b)
