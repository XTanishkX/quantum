"""Noise-aware testing: run against a real IBM device's calibration snapshot.

The ideal-simulator threshold (0.05) would be far too strict under hardware
noise; here the check encodes "still recognizably a Bell state on real
hardware" instead. Requires: pip install 'qontinuum[ibm]'.
"""

from qiskit import QuantumCircuit

from qontinuum import assert_distribution, qtest


@qtest(shots=4000, backend="ibm:manila")
def bell_pair_on_hardware_noise():
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


@bell_pair_on_hardware_noise.check
def survives_real_calibration_noise(result):
    assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.2)
