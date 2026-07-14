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
    """Build a simulator from a backend spec via the plugin registry.

    The token before the first ``:`` selects the backend plugin (``aer`` or
    ``ibm`` built in); the remainder is passed to it (e.g. ``fake_manila`` for
    ``ibm:fake_manila``). Third-party backend plugins resolve identically.
    """
    from qontinuum.plugins import get_registry

    name, _, arg = spec.partition(":")
    record = get_registry().get("backend", name)
    if record is None or not record.available:
        raise BackendSpecError(
            f"unknown backend spec {spec!r}; expected 'aer' or 'ibm:<device>'"
        )
    return record.plugin.build(arg)


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
