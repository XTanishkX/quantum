"""Snapshot testing: pin a GHZ state's distribution as a golden baseline."""

from qiskit import QuantumCircuit

from qontinuum import assert_fidelity, qtest


@qtest(shots=4000, snapshot=True)
def ghz_5():
    qc = QuantumCircuit(5)
    qc.h(0)
    for i in range(4):
        qc.cx(i, i + 1)
    qc.measure_all()
    return qc


@ghz_5.check
def collapses_to_all_zeros_or_all_ones(result):
    assert_fidelity(result, {"00000": 0.5, "11111": 0.5}, min_fidelity=0.98)
