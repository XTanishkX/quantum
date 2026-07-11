"""Structural canonical form and content hash for quantum circuits.

Two circuits get the same hash when they apply the same operations, with the
same parameters, to the same qubit/clbit positions, in the same order —
regardless of register names, circuit names, metadata, or the QASM formatting
they were loaded from. This is *structural* equivalence, not unitary
equivalence (which is intractable in general): ``rz(pi); rz(pi)`` and
``rz(2*pi)`` hash differently.

The canonical form is versioned (``format`` field) so hashes are comparable
across Qontinuum releases; any change to the serialization bumps the version.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import ControlFlowOp

CANON_FORMAT = "qontinuum-canon-1"

# Parameters are rounded before hashing so float repr noise (e.g. values that
# differ only past the 12th decimal after algebraically identical constructions)
# does not produce distinct hashes.
_PARAM_DECIMALS = 12


def canonical_form(circuit: QuantumCircuit) -> dict[str, Any]:
    """Return a JSON-serializable canonical description of the circuit."""
    return {
        "format": CANON_FORMAT,
        "num_qubits": circuit.num_qubits,
        "num_clbits": circuit.num_clbits,
        "ops": _canonical_ops(circuit),
    }


def circuit_hash(circuit: QuantumCircuit) -> str:
    """Content-address a circuit: ``sha256:<hex digest>`` of its canonical form."""
    payload = json.dumps(canonical_form(circuit), separators=(",", ":"), sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _canonical_ops(circuit: QuantumCircuit) -> list[list[Any]]:
    ops: list[list[Any]] = []
    for instruction in circuit.data:
        op = instruction.operation
        qubits = [circuit.find_bit(q).index for q in instruction.qubits]
        clbits = [circuit.find_bit(c).index for c in instruction.clbits]
        entry: list[Any] = [op.name, _canonical_params(op.params), qubits, clbits]
        if isinstance(op, ControlFlowOp):
            entry.append([_canonical_ops(block) for block in op.blocks])
        ops.append(entry)
    return ops


def _canonical_params(params: list[Any]) -> list[Any]:
    out: list[Any] = []
    for p in params:
        if isinstance(p, (int, float, np.integer, np.floating)):
            rounded = round(float(p), _PARAM_DECIMALS)
            # Avoid distinct hashes for 0.0 vs -0.0.
            out.append(rounded + 0.0)
        elif isinstance(p, QuantumCircuit):
            out.append(canonical_form(p))
        else:
            out.append(str(p))
    return out
