"""The plugins Qontinuum ships with — the reference implementations.

Each is a plain object satisfying one of the protocols in
:mod:`qontinuum.plugins.base`. Heavy / optional imports (SDKs, provider
clients) stay lazy inside the methods so importing this module is cheap and
never fails, even when the optional extras are missing.

Reading these is the fastest way to learn how to write your own plugin — see
``docs/plugins.md`` for the entry-point wiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from qiskit import QuantumCircuit

    from qontinuum.hardware.base import HardwareAdapter


# --------------------------------------------------------------------------- #
# Providers (hardware execution)
# --------------------------------------------------------------------------- #
class IBMProvider:
    name = "ibm"
    catalog_key = "ibm"
    requires = ("qiskit_ibm_runtime",)
    extra = "ibm"
    summary = "IBM Quantum hardware via Qiskit Runtime SamplerV2."

    def build_adapter(self, device: str) -> HardwareAdapter:
        from qontinuum.hardware.ibm import IBMAdapter

        return IBMAdapter(device)

    def catalog_fragment(self) -> dict | None:
        return None


class BraketProvider:
    name = "braket"
    catalog_key = "braket"
    requires = ("braket", "qiskit_braket_provider")
    extra = "braket"
    summary = "QPUs on AWS Braket (IonQ, Rigetti, IQM)."

    def build_adapter(self, device: str) -> HardwareAdapter:
        from qontinuum.hardware.braket import BraketAdapter

        return BraketAdapter(device)

    def catalog_fragment(self) -> dict | None:
        return None


# --------------------------------------------------------------------------- #
# Backends (local simulation)
# --------------------------------------------------------------------------- #
class AerBackend:
    name = "aer"
    requires: tuple[str, ...] = ()
    extra = None
    summary = "Ideal (noiseless) local Aer simulation."

    def build(self, arg: str) -> Any:
        from qiskit_aer import AerSimulator

        return AerSimulator()


class IBMNoiseBackend:
    name = "ibm"
    requires = ("qiskit_ibm_runtime",)
    extra = "ibm"
    summary = "Local Aer simulation under a named IBM device's noise model."

    def build(self, arg: str) -> Any:
        from qontinuum.noise import noisy_simulator

        return noisy_simulator(arg)


# --------------------------------------------------------------------------- #
# SDKs (foreign circuit object -> Qiskit IR)
# --------------------------------------------------------------------------- #
class QiskitSDK:
    name = "qiskit"
    requires: tuple[str, ...] = ()
    extra = None
    summary = "Native Qiskit QuantumCircuit (the canonical IR)."

    def matches(self, source: Any) -> bool:
        from qiskit import QuantumCircuit

        return isinstance(source, QuantumCircuit)

    def to_qiskit(self, source: Any) -> QuantumCircuit:
        return source


class CirqSDK:
    name = "cirq"
    requires = ("cirq",)
    extra = None
    summary = "Google Cirq circuits, via Cirq's QASM exporter."

    def matches(self, source: Any) -> bool:
        return (type(source).__module__ or "").startswith("cirq")

    def to_qiskit(self, source: Any) -> QuantumCircuit:
        from qontinuum.circuits.loader import CircuitLoadError, _load_qasm

        try:
            import cirq
        except ImportError as exc:  # pragma: no cover - source implies cirq exists
            raise CircuitLoadError("got a cirq object but cirq is not importable") from exc
        try:
            return _load_qasm(cirq.qasm(source), origin=f"cirq:{type(source).__name__}")
        except CircuitLoadError:
            raise
        except Exception as exc:
            raise CircuitLoadError(
                f"cirq circuit could not be exported to QASM: {exc}"
            ) from exc


class PennylaneSDK:
    name = "pennylane"
    requires = ("pennylane",)
    extra = None
    summary = "PennyLane QuantumTapes, via PennyLane's OpenQASM exporter."

    def matches(self, source: Any) -> bool:
        return (type(source).__module__ or "").startswith("pennylane")

    def to_qiskit(self, source: Any) -> QuantumCircuit:
        from qontinuum.circuits.loader import CircuitLoadError, _load_qasm

        try:
            import pennylane as qml
        except ImportError as exc:  # pragma: no cover - source implies pennylane exists
            raise CircuitLoadError(
                "got a pennylane object but pennylane is not importable"
            ) from exc
        if isinstance(source, qml.QNode):
            raise CircuitLoadError(
                "pass a pennylane QuantumTape (e.g. qml.workflow.construct_tape(qnode)(*args)), "
                "not the QNode itself — a QNode has no circuit until called with arguments"
            )
        if not isinstance(source, qml.tape.QuantumScript):
            raise CircuitLoadError(
                f"unsupported pennylane object {type(source).__name__}; expected a QuantumTape"
            )
        try:
            # qml.to_openqasm is the current API; tape.to_openqasm existed pre-0.45.
            exporter = getattr(qml, "to_openqasm", None) or type(source).to_openqasm
            return _load_qasm(exporter(source), origin=f"pennylane:{type(source).__name__}")
        except CircuitLoadError:
            raise
        except Exception as exc:
            raise CircuitLoadError(
                f"pennylane tape could not be exported to QASM: {exc}"
            ) from exc


def builtin_plugins() -> dict[str, list[Any]]:
    """The plugins shipped in this package, grouped by kind.

    Order within a kind is the discovery/priority order (first match wins for
    SDKs). Names are unique within a kind.
    """
    return {
        "provider": [IBMProvider(), BraketProvider()],
        "backend": [AerBackend(), IBMNoiseBackend()],
        "sdk": [QiskitSDK(), CirqSDK(), PennylaneSDK()],
    }
