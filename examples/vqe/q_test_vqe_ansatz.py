"""Variational-workflow regression test.

A common real-world pattern: parameters were optimized offline (expensively),
and CI's job is to guarantee the *ansatz circuit* still produces the same
state for those parameters after refactors and dependency bumps. The snapshot
pins the full distribution; the fidelity check documents the physics.
"""

import numpy as np
from qiskit import QuantumCircuit

from qontinuum import assert_fidelity, qtest

OPTIMIZED_THETAS = [np.pi / 2, 0.0, 0.0, np.pi / 4]


def ansatz(thetas) -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.ry(thetas[0], 0)
    qc.ry(thetas[1], 1)
    qc.cx(0, 1)
    qc.ry(thetas[2], 0)
    qc.ry(thetas[3], 1)
    qc.measure_all()
    return qc


@qtest(shots=6000, snapshot=True)
def optimized_ansatz():
    return ansatz(OPTIMIZED_THETAS)


@optimized_ansatz.check
def matches_reference_state(result):
    # Reference distribution computed analytically for OPTIMIZED_THETAS:
    # cos^2(pi/8)/2 on the even-parity states, sin^2(pi/8)/2 on odd parity.
    expected = {"00": 0.4267767, "01": 0.0732233, "10": 0.0732233, "11": 0.4267767}
    assert_fidelity(result, expected, min_fidelity=0.99)
