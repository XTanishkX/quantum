"""Extract the circuit features that provider pricing formulas consume."""

from __future__ import annotations

from dataclasses import dataclass

from qiskit import QuantumCircuit

_NON_GATES = {"barrier", "delay", "snapshot"}
_SPAM = {"measure", "reset", "initialize"}


@dataclass(frozen=True)
class CircuitProfile:
    num_qubits: int
    depth: int
    n_1q_gates: int
    n_2q_gates: int
    n_multi_qubit_gates_expanded: int  # multi-controlled gates as 6*(n-2) two-qubit gates
    n_spam: int  # state prep + measure + reset (prep counted once per qubit)
    n_measurements: int  # measure instructions only

    @property
    def n_2q_effective(self) -> int:
        """Two-qubit gate count with multi-qubit gates expanded (IonQ billing rule)."""
        return self.n_2q_gates + self.n_multi_qubit_gates_expanded


def profile_circuit(circuit: QuantumCircuit) -> CircuitProfile:
    n_1q = n_2q = n_multi = n_measure = 0
    n_spam = circuit.num_qubits  # implicit initial state preparation
    for instruction in circuit.data:
        name = instruction.operation.name
        if name in _NON_GATES:
            continue
        if name in _SPAM:
            n_spam += 1
            if name == "measure":
                n_measure += 1
            continue
        arity = len(instruction.qubits)
        if arity <= 1:
            n_1q += 1
        elif arity == 2:
            n_2q += 1
        else:
            # Providers bill an n-qubit controlled gate as 6*(n-2) two-qubit gates.
            n_multi += 6 * (arity - 2)
    return CircuitProfile(
        num_qubits=circuit.num_qubits,
        depth=circuit.depth(),
        n_1q_gates=n_1q,
        n_2q_gates=n_2q,
        n_multi_qubit_gates_expanded=n_multi,
        n_spam=n_spam,
        n_measurements=n_measure,
    )
