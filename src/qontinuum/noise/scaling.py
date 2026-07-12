"""Parametric and scaled noise models — load-testing for quantum circuits.

Instead of mutating a device's full noise-model dict (opaque, fragile), we
distill a device to three interpretable knobs — median 1q error, 2q error,
readout error — and rebuild a transparent depolarizing+readout model at any
scale factor. Scale 1.0 approximates today's device; scale 2.0 is a device
twice as noisy; scale 0 is ideal.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, ReadoutError, depolarizing_error

_1Q_GATES = ["sx", "x", "h", "ry", "rx"]
_2Q_GATES = ["cx", "cz", "ecr", "swap"]
_MAX_1Q = 0.75  # depolarizing probability caps (physical validity)
_MAX_2Q = 0.9375
_MAX_RO = 0.5


@dataclass(frozen=True)
class NoiseProfile:
    error_1q: float
    error_2q: float
    error_readout: float

    def scaled(self, factor: float) -> NoiseProfile:
        return NoiseProfile(
            error_1q=min(self.error_1q * factor, _MAX_1Q),
            error_2q=min(self.error_2q * factor, _MAX_2Q),
            error_readout=min(self.error_readout * factor, _MAX_RO),
        )


def profile_from_device(device: str) -> NoiseProfile:
    """Median error rates from an IBM calibration source (bundled or @live)."""
    from qontinuum.cli_groups.device_cmds import _target_backend

    backend = _target_backend(device)
    target = backend.target

    def med(op_names: list[str]) -> float:
        vals: list[float] = []
        for op in op_names:
            if op not in target.operation_names:
                continue
            for props in target[op].values():
                if props is not None and getattr(props, "error", None) is not None:
                    vals.append(props.error)
        return statistics.median(vals) if vals else 0.0

    return NoiseProfile(
        error_1q=med(["sx", "x"]),
        error_2q=med(["cz", "ecr", "cx"]),
        error_readout=med(["measure"]),
    )


def simulator_for(profile: NoiseProfile) -> AerSimulator:
    """Transparent depolarizing + symmetric-readout simulator for a profile."""
    model = NoiseModel()
    if profile.error_1q > 0:
        model.add_all_qubit_quantum_error(depolarizing_error(profile.error_1q, 1), _1Q_GATES)
    if profile.error_2q > 0:
        model.add_all_qubit_quantum_error(depolarizing_error(profile.error_2q, 2), _2Q_GATES)
    if profile.error_readout > 0:
        p = profile.error_readout
        model.add_all_qubit_readout_error(ReadoutError([[1 - p, p], [p, 1 - p]]))
    return AerSimulator(noise_model=model)


def run_at_scale(circuit, *, device: str, scale: float, shots: int, seed: int | None):
    """Execute a circuit under a device's noise profile scaled by ``scale``."""
    from qiskit import transpile

    from qontinuum.assertions.stats import normalize_counts

    profile = profile_from_device(device).scaled(scale)
    backend = simulator_for(profile)
    transpiled = transpile(circuit, backend, seed_transpiler=seed)
    job = backend.run(transpiled, shots=shots, seed_simulator=seed)
    return normalize_counts(job.result().get_counts()), profile
