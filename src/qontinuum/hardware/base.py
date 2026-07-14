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
    """Build an adapter from an ``--on`` spec: ``<provider>:<device>``.

    Providers are resolved through the plugin registry, so ``ibm`` and
    ``braket`` are the built-ins and any installed third-party provider plugin
    works the same way.
    """
    from qontinuum.plugins import get_registry

    provider, _, device = spec.partition(":")
    if not device:
        raise HardwareError(
            f"invalid hardware spec {spec!r}; expected '<provider>:<device>' "
            f"(e.g. 'ibm:ibm_brisbane' or 'braket:ionq_forte')"
        )
    registry = get_registry()
    record = registry.get("provider", provider)
    if record is None:
        supported = ", ".join(registry.names("provider")) or "none"
        raise HardwareError(
            f"unknown hardware provider {provider!r} (supported: {supported})"
        )
    if not record.available:
        raise HardwareError(
            f"hardware provider {provider!r} failed to load: {record.error}"
        )
    try:
        return record.plugin.build_adapter(device)
    except HardwareError:
        raise
    except Exception as exc:
        raise HardwareError(
            f"provider {provider!r} could not build an adapter for {device!r}: {exc}"
        ) from exc
