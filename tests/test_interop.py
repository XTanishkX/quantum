"""Cross-SDK loading: cirq and pennylane objects into the qiskit-based runner.

These tests skip when the SDK isn't installed; CI installs both so interop is
exercised there.
"""

import pytest

from qontinuum.circuits import CircuitLoadError, circuit_hash, load_circuit
from qontinuum.runner.backends import execute


class TestCirq:
    cirq = pytest.importorskip("cirq")

    def bell(self):
        cirq = self.cirq
        q0, q1 = cirq.LineQubit.range(2)
        return cirq.Circuit(
            [cirq.H(q0), cirq.CNOT(q0, q1), cirq.measure(q0, q1, key="m")]
        )

    def test_loads_cirq_circuit(self):
        qc = load_circuit(self.bell())
        assert qc.num_qubits == 2
        assert qc.num_clbits == 2

    def test_cirq_bell_behaves_like_qiskit_bell(self):
        run = execute(load_circuit(self.bell()), shots=2000, seed=3)
        keys = set(run.counts)
        assert keys <= {"00", "11"}
        assert sum(run.counts.values()) == 2000

    def test_cirq_circuit_hashes_stably(self):
        assert circuit_hash(load_circuit(self.bell())) == circuit_hash(
            load_circuit(self.bell())
        )


class TestPennylane:
    qml = pytest.importorskip("pennylane")

    def bell_tape(self):
        qml = self.qml
        ops = [qml.Hadamard(wires=0), qml.CNOT(wires=[0, 1])]
        measurements = [qml.sample(wires=[0, 1])]
        return qml.tape.QuantumTape(ops, measurements, shots=100)

    def test_loads_pennylane_tape(self):
        qc = load_circuit(self.bell_tape())
        assert qc.num_qubits == 2

    def test_pennylane_bell_distribution(self):
        run = execute(load_circuit(self.bell_tape()), shots=2000, seed=3)
        assert set(run.counts) <= {"00", "11"}

    def test_qnode_rejected_with_guidance(self):
        qml = self.qml
        dev = qml.device("default.qubit", wires=1)

        @qml.qnode(dev)
        def circuit():
            qml.Hadamard(wires=0)
            return qml.sample(wires=[0])

        with pytest.raises(CircuitLoadError, match="QuantumTape"):
            load_circuit(circuit)


def test_unrelated_object_still_rejected():
    with pytest.raises(CircuitLoadError, match="Unsupported circuit source"):
        load_circuit(42)
