"""Load quantum circuits from Qiskit objects, QASM strings, or files."""

from __future__ import annotations

from pathlib import Path

from qiskit import QuantumCircuit


class CircuitLoadError(ValueError):
    """Raised when a circuit source cannot be parsed."""


def load_circuit(source) -> QuantumCircuit:
    """Load a circuit from a QuantumCircuit, QASM string/file, or any SDK plugin.

    QASM 2 and QASM 3 are both accepted; the dialect is detected from the
    ``OPENQASM`` header (defaulting to QASM 3 when absent). Foreign circuit
    objects (Cirq, PennyLane, and any installed third-party SDK) are converted
    through the plugin registry — no hard dependency on any single SDK.
    """
    if isinstance(source, QuantumCircuit):
        return source
    if isinstance(source, Path):
        return _load_qasm(source.read_text(), origin=str(source))
    if isinstance(source, str):
        maybe_path = Path(source)
        try:
            is_file = maybe_path.is_file()
        except OSError:
            is_file = False
        if is_file:
            return _load_qasm(maybe_path.read_text(), origin=source)
        if "OPENQASM" in source or "qubit" in source:
            return _load_qasm(source, origin="<string>")
        raise CircuitLoadError(
            f"Not a QASM string and no such file: {source!r}"
        )
    converted = _from_sdk_plugin(source)
    if converted is not None:
        return converted
    raise CircuitLoadError(f"Unsupported circuit source type: {type(source).__name__}")


def _from_sdk_plugin(source) -> QuantumCircuit | None:
    """Convert a foreign object via the first SDK plugin that claims it."""
    from qontinuum.plugins import get_registry

    for plugin in get_registry().available("sdk"):
        try:
            claimed = plugin.matches(source)
        except Exception:  # a misbehaving plugin must not break loading
            continue
        if claimed:
            return plugin.to_qiskit(source)
    return None


def _load_qasm(text: str, origin: str) -> QuantumCircuit:
    header = next(
        (line for line in text.splitlines() if line.strip().startswith("OPENQASM")), ""
    )
    try:
        if "2.0" in header:
            from qiskit import qasm2

            return qasm2.loads(text)
        from qiskit import qasm3

        return qasm3.loads(text)
    except Exception as exc:
        raise CircuitLoadError(f"Failed to parse QASM from {origin}: {exc}") from exc
