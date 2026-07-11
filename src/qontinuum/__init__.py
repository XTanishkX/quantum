"""Qontinuum: CI/CD, noise-aware regression testing, and cost intelligence for quantum programs."""

__version__ = "0.1.0"

from qontinuum.assertions import (
    QuantumAssertionError,
    StatisticallyUnsoundError,
    assert_chi_squared,
    assert_distribution,
    assert_fidelity,
    assert_matches_baseline,
    assert_probability,
)
from qontinuum.circuits import circuit_hash, load_circuit
from qontinuum.runner import QuantumTest, RunResult, execute, qtest

__all__ = [
    "QuantumAssertionError",
    "QuantumTest",
    "RunResult",
    "StatisticallyUnsoundError",
    "assert_chi_squared",
    "assert_distribution",
    "assert_fidelity",
    "assert_matches_baseline",
    "assert_probability",
    "circuit_hash",
    "execute",
    "load_circuit",
    "qtest",
]
