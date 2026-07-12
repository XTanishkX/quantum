"""Benchmark engines: mirror circuits, RB-lite decay fits, QV-style estimates.

All three are *estimates on a noise model* unless pointed at hardware — every
result is labeled as such. The value is comparative (device A vs B, this week
vs last week), not absolute certification.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from qiskit import QuantumCircuit

from qontinuum.assertions.stats import normalize_counts


def _execute(circuit: QuantumCircuit, backend_spec: str, shots: int, seed: int | None):
    from qontinuum.runner.backends import execute

    return execute(circuit, shots=shots, backend_spec=backend_spec, seed=seed).counts


def mirror_survival(
    circuit: QuantumCircuit, *, backend_spec: str, shots: int, seed: int | None = 7
) -> float:
    """P(all-zeros) of U·U† — 1.0 on a perfect device, decays with total error."""
    bare = circuit.remove_final_measurements(inplace=False)
    mirrored = bare.compose(bare.inverse())
    mirrored.measure_all()
    counts = normalize_counts(_execute(mirrored, backend_spec, shots, seed))
    zeros = "0" * mirrored.num_qubits
    return counts.get(zeros, 0) / shots


@dataclass(frozen=True)
class RBResult:
    lengths: list[int]
    survivals: list[float]
    decay_p: float
    error_per_layer: float  # r = (1-p)(2^n - 1)/2^n


def rb_lite(
    *,
    qubits: int = 2,
    lengths: tuple[int, ...] = (1, 2, 4, 8, 16, 32),
    trials: int = 3,
    shots: int = 1000,
    backend_spec: str = "aer",
    seed: int = 7,
) -> RBResult:
    """Mirror-RB-lite: random layers, mirrored, exponential decay fit.

    Not Clifford RB (no group twirling) — a lightweight proxy whose decay
    constant tracks the same physics and is comparable across backends.
    """
    from scipy.optimize import curve_fit

    rng = np.random.default_rng(seed)
    survivals: list[float] = []
    for length in lengths:
        values = []
        for trial in range(trials):
            circuit = _random_layers(qubits, length, rng)
            values.append(
                mirror_survival(circuit, backend_spec=backend_spec, shots=shots,
                                seed=seed + trial)
            )
        survivals.append(float(np.mean(values)))

    floor = 1 / 2**qubits

    def model(m, a, p):
        return a * p**m + floor

    try:
        (_a, p), _ = curve_fit(
            model, np.array(lengths, dtype=float), np.array(survivals),
            p0=[1 - floor, 0.98], bounds=([0, 0], [1, 1]), maxfev=5000,
        )
    except Exception:
        p = 1.0
    error_per_layer = (1 - p) * (2**qubits - 1) / 2**qubits
    return RBResult(list(lengths), [round(s, 4) for s in survivals],
                    round(float(p), 5), round(float(error_per_layer), 5))


def _random_layers(qubits: int, layers: int, rng: np.random.Generator) -> QuantumCircuit:
    circuit = QuantumCircuit(qubits)
    one_qubit_gates = ["h", "x", "s", "t", "sdg"]
    for _ in range(layers):
        for q in range(qubits):
            getattr(circuit, one_qubit_gates[rng.integers(len(one_qubit_gates))])(q)
        if qubits >= 2:
            a = int(rng.integers(qubits - 1))
            circuit.cx(a, a + 1)
    return circuit


@dataclass(frozen=True)
class QVResult:
    passed_widths: list[int]
    failed_width: int | None
    quantum_volume_estimate: int
    heavy_output_probs: dict[int, float]


def qv_estimate(
    *,
    max_qubits: int = 5,
    trials: int = 10,
    shots: int = 500,
    backend_spec: str = "aer",
    seed: int = 7,
) -> QVResult:
    """Quantum-volume-style estimate: heavy-output probability > 2/3 per width.

    Simplified from the certified protocol (fewer trials, no 2-sigma bound) —
    an *estimate* for tracking noise models over time, not a QV claim.
    """
    from qiskit.circuit.library import QuantumVolume
    from qiskit.quantum_info import Statevector

    passed: list[int] = []
    hops: dict[int, float] = {}
    failed: int | None = None
    for width in range(2, max_qubits + 1):
        trial_hops = []
        for trial in range(trials):
            model = QuantumVolume(width, depth=width, seed=seed + 97 * trial + width)
            ideal_probs = np.abs(Statevector(model).data) ** 2
            median = float(np.median(ideal_probs))
            heavy = {format(i, f"0{width}b") for i, p in enumerate(ideal_probs) if p > median}
            measured = model.copy()
            measured.measure_all()
            counts = normalize_counts(
                _execute(measured, backend_spec, shots, seed + trial)
            )
            trial_hops.append(sum(v for k, v in counts.items() if k in heavy) / shots)
        hop = float(np.mean(trial_hops))
        hops[width] = round(hop, 4)
        if hop > 2 / 3:
            passed.append(width)
        else:
            failed = width
            break
    qv = 2 ** max(passed) if passed else 1
    return QVResult(passed, failed, qv, hops)
