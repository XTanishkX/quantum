"""Load quantum circuits from Qiskit objects, QASM strings, or files."""

from __future__ import annotations

from pathlib import Path

from qiskit import QuantumCircuit


class CircuitLoadError(ValueError):
    """Raised when a circuit source cannot be parsed."""


def load_circuit(source) -> QuantumCircuit:
    """Load a circuit from a QuantumCircuit, QASM string/file, Cirq, or PennyLane.

    QASM 2 and QASM 3 are both accepted; the dialect is detected from the
    ``OPENQASM`` header (defaulting to QASM 3 when absent). Cirq circuits and
    PennyLane tapes are converted through their own QASM exporters — no hard
    dependency on either SDK; whichever produced the object is already
    importable.
    """
    if isinstance(source, QuantumCircuit):
        return source
    module = type(source).__module__ or ""
    if module.startswith("cirq"):
        return _from_cirq(source)
    if module.startswith("pennylane"):
        return _from_pennylane(source)
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


def _from_cirq(source) -> QuantumCircuit:
    try:
        import cirq
    except ImportError as exc:  # pragma: no cover - source object implies cirq exists
        raise CircuitLoadError("got a cirq object but cirq is not importable") from exc
    try:
        return _load_qasm(cirq.qasm(source), origin=f"cirq:{type(source).__name__}")
    except CircuitLoadError:
        raise
    except Exception as exc:
        raise CircuitLoadError(f"cirq circuit could not be exported to QASM: {exc}") from exc


def _from_pennylane(source) -> QuantumCircuit:
    try:
        import pennylane as qml
    except ImportError as exc:  # pragma: no cover - source object implies pennylane exists
        raise CircuitLoadError("got a pennylane object but pennylane is not importable") from exc
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
        raise CircuitLoadError(f"pennylane tape could not be exported to QASM: {exc}") from exc


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
