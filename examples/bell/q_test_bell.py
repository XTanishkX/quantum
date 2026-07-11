"""The 'hello world' of quantum testing: a Bell pair must be maximally entangled."""

from qiskit import QuantumCircuit

from qontinuum import assert_distribution, assert_probability, qtest


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
def no_odd_parity_leakage(result):
    assert_probability(result, "01", max_p=0.01)
    assert_probability(result, "10", max_p=0.01)
