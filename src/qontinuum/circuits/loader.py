"""Load quantum circuits from Qiskit objects, QASM strings, or files."""

from __future__ import annotations

from pathlib import Path

from qiskit import QuantumCircuit


class CircuitLoadError(ValueError):
    """Raised when a circuit source cannot be parsed."""


def load_circuit(source: QuantumCircuit | str | Path) -> QuantumCircuit:
    """Load a circuit from a QuantumCircuit, a QASM string, or a .qasm file path.

    QASM 2 and QASM 3 are both accepted; the dialect is detected from the
    ``OPENQASM`` header (defaulting to QASM 3 when absent).
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
    raise CircuitLoadError(f"Unsupported circuit source type: {type(source).__name__}")


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
