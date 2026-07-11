"""Adapter interface for submitting circuits to real quantum hardware."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from qiskit import QuantumCircuit


class HardwareError(RuntimeError):
    """Submission failed or the adapter cannot be constructed."""


class SpendGuardError(RuntimeError):
    """The estimated cost exceeds the allowed budget; nothing was submitted."""


@runtime_checkable
class HardwareAdapter(Protocol):
    """One per provider; wraps auth, transpilation, submission, and counts."""

    #: Human-readable target, e.g. "ibm_brisbane" or "braket:rigetti_cepheus".
    target: str
    #: Catalog (provider_key, device_key) used for pre-run cost estimation.
    catalog_device: tuple[str, str]

    def submit(self, circuit: QuantumCircuit, shots: int) -> dict[str, int]:
        """Run the circuit and return measurement counts. Blocking."""
        ...


def resolve_adapter(spec: str) -> HardwareAdapter:
    """Build an adapter from an ``--on`` spec: ``ibm:<backend>`` or ``braket:<device>``."""
    provider, _, device = spec.partition(":")
    if not device:
        raise HardwareError(
            f"invalid hardware spec {spec!r}; expected 'ibm:<backend>' or 'braket:<device>'"
        )
    if provider == "ibm":
        from qontinuum.hardware.ibm import IBMAdapter

        return IBMAdapter(device)
    if provider == "braket":
        from qontinuum.hardware.braket import BraketAdapter

        return BraketAdapter(device)
    raise HardwareError(f"unknown hardware provider {provider!r} (supported: ibm, braket)")
