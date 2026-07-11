"""Backend resolution and circuit execution.

Backend specs are strings so test files stay declarative:

- ``"aer"`` — ideal (noiseless) local simulation.
- ``"ibm:<device>"`` — local Aer simulation under a noise model built from the
  named IBM device's calibration data (see :mod:`qontinuum.noise`).
"""

from __future__ import annotations

import time

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

from qontinuum.assertions.stats import normalize_counts
from qontinuum.circuits import circuit_hash
from qontinuum.runner.result import RunResult


class BackendSpecError(ValueError):
    """The backend spec string is not recognized."""


def resolve_backend(spec: str) -> AerSimulator:
    if spec == "aer":
        return AerSimulator()
    if spec.startswith("ibm:"):
        from qontinuum.noise import noisy_simulator

        return noisy_simulator(spec.removeprefix("ibm:"))
    raise BackendSpecError(
        f"unknown backend spec {spec!r}; expected 'aer' or 'ibm:<device>'"
    )


def execute(
    circuit: QuantumCircuit,
    *,
    shots: int,
    backend_spec: str = "aer",
    seed: int | None = None,
) -> RunResult:
    """Transpile and run a circuit, returning normalized counts."""
    backend = resolve_backend(backend_spec)
    start = time.perf_counter()
    transpiled = transpile(circuit, backend, seed_transpiler=seed)
    job = backend.run(transpiled, shots=shots, seed_simulator=seed)
    counts = normalize_counts(job.result().get_counts())
    duration_ms = (time.perf_counter() - start) * 1000
    return RunResult(
        counts=counts,
        shots=shots,
        backend=backend_spec,
        circuit_hash=circuit_hash(circuit),
        seed=seed,
        duration_ms=duration_ms,
    )
