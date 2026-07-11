"""Algorithm regression test: 2-qubit Grover search finds |11> with certainty.

On two qubits a single Grover iteration amplifies the marked state to
probability 1 (up to sampling and gate noise) — a crisp end-to-end check
that oracle + diffuser still work after refactoring.
"""

from qiskit import QuantumCircuit

from qontinuum import assert_probability, qtest


@qtest(shots=2000)
def grover_finds_11():
    qc = QuantumCircuit(2)
    qc.h([0, 1])
    qc.cz(0, 1)  # oracle marking |11>
    qc.h([0, 1])  # diffuser (for n=2, H-Z-CZ-H structure)
    qc.z([0, 1])
    qc.cz(0, 1)
    qc.h([0, 1])
    qc.measure_all()
    return qc


@grover_finds_11.check
def marked_state_dominates(result):
    assert_probability(result, "11", min_p=0.99)
