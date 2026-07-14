"""Plugin contracts for the three pluggable edges of Qontinuum.

Qontinuum keeps Qiskit's :class:`~qiskit.circuit.QuantumCircuit` as its single
canonical intermediate representation. Everything in the core — the ``@qtest``
runner, cost estimation, routing, snapshots — speaks that IR. The *edges* that
touch the outside world are pluggable:

- **Providers** submit circuits to real hardware (``qont run --on ibm:…``).
- **Backends** build local simulators (``@qtest(backend="ibm:fake_manila")``).
- **SDKs** convert a foreign circuit object (Cirq, PennyLane, …) *into* the IR.

Each kind is a small typed :class:`~typing.Protocol`. Third-party packages ship
plugins by declaring entry points in one of these groups:

    [project.entry-points."qontinuum.providers"]
    foo = "my_pkg:foo_provider"

The registry (:mod:`qontinuum.plugins.registry`) discovers them alongside the
built-ins and never lets a broken one crash the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from qiskit import QuantumCircuit

    from qontinuum.hardware.base import HardwareAdapter

#: The three plugin kinds and the entry-point group each is discovered from.
ENTRY_POINT_GROUPS: dict[str, str] = {
    "provider": "qontinuum.providers",
    "backend": "qontinuum.backends",
    "sdk": "qontinuum.sdks",
}


class PluginError(RuntimeError):
    """A plugin could not be loaded, resolved, or built."""


@runtime_checkable
class ProviderPlugin(Protocol):
    """Submits circuits to a hardware provider and prices them.

    ``name`` is the ``--on`` scheme (e.g. ``"ibm"`` in ``ibm:brisbane``).
    ``catalog_key`` is the provider id its devices are priced under in the cost
    catalog. ``catalog_fragment`` is optional: return a
    ``{"display": ..., "devices": {...}}`` mapping to contribute pricing and
    routing-quality data for devices not already in the bundled catalog.
    """

    name: str
    catalog_key: str

    def build_adapter(self, device: str) -> HardwareAdapter:
        """Construct an adapter for one device. May raise ``HardwareError``."""
        ...


@runtime_checkable
class BackendPlugin(Protocol):
    """Builds a local simulator from the part of the spec after ``name:``.

    For ``backend="ibm:fake_manila"`` the registry routes to the plugin named
    ``"ibm"`` and calls ``build("fake_manila")``. For a bare ``"aer"`` spec the
    argument is the empty string.
    """

    name: str

    def build(self, arg: str) -> Any:
        """Return an Aer-compatible backend (supports ``transpile`` + ``run``)."""
        ...


@runtime_checkable
class SDKPlugin(Protocol):
    """Converts a foreign circuit object into a Qiskit ``QuantumCircuit``."""

    name: str

    def matches(self, source: Any) -> bool:
        """True if this plugin can convert ``source``. Must not raise."""
        ...

    def to_qiskit(self, source: Any) -> QuantumCircuit:
        """Convert ``source`` to the canonical IR. May raise ``CircuitLoadError``."""
        ...


@dataclass(frozen=True)
class PluginRecord:
    """What discovery found for one plugin — available or not."""

    name: str
    kind: str  # "provider" | "backend" | "sdk"
    source: str  # "builtin" | "entrypoint"
    available: bool
    summary: str = ""
    requires: tuple[str, ...] = ()  # importable module names it needs to function
    extra: str | None = None  # pip extra that provides `requires`, if any
    dist: str | None = None  # distribution that shipped an entry point
    error: str | None = None  # why it failed to load, if unavailable
    shadows: str | None = None  # source of a same-named plugin it overrode
    plugin: Any = field(default=None, repr=False, compare=False)

    def install_hint(self) -> str | None:
        """A concrete ``pip install`` line to make this plugin functional."""
        if not self.requires:
            return None
        if self.extra:
            return f"pip install 'qontinuum[{self.extra}]'"
        return "pip install " + " ".join(self.requires)
