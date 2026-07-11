"""Op-level diff between two circuits' canonical forms — git diff for circuits.

Because the diff runs on the canonical form (register names, circuit names,
and QASM formatting normalized away), it shows only *semantic* changes: gates
added, removed, or re-targeted.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from qiskit import QuantumCircuit

from qontinuum.circuits.hashing import canonical_form, circuit_hash


@dataclass(frozen=True)
class DiffLine:
    tag: str  # " ", "-", "+"
    text: str


@dataclass(frozen=True)
class CircuitDiff:
    hash_a: str
    hash_b: str
    lines: list[DiffLine]

    @property
    def identical(self) -> bool:
        return self.hash_a == self.hash_b

    @property
    def n_added(self) -> int:
        return sum(1 for line in self.lines if line.tag == "+")

    @property
    def n_removed(self) -> int:
        return sum(1 for line in self.lines if line.tag == "-")


def _format_op(op: list) -> str:
    name, params, qubits, clbits, *blocks = op
    parts = [name]
    if params:
        rendered = ", ".join(
            f"{p:.6g}" if isinstance(p, int | float) else "<block>" for p in params
        )
        parts.append(f"({rendered})")
    parts.append(" q" + str(qubits))
    if clbits:
        parts.append(" -> c" + str(clbits))
    if blocks:
        parts.append(f"  [{sum(len(b) for b in blocks[0])} nested ops]")
    return "".join(parts)


def diff_circuits(a: QuantumCircuit, b: QuantumCircuit) -> CircuitDiff:
    form_a, form_b = canonical_form(a), canonical_form(b)
    ops_a = [_format_op(op) for op in form_a["ops"]]
    ops_b = [_format_op(op) for op in form_b["ops"]]

    lines: list[DiffLine] = []
    if form_a["num_qubits"] != form_b["num_qubits"]:
        lines.append(DiffLine("-", f"qubits: {form_a['num_qubits']}"))
        lines.append(DiffLine("+", f"qubits: {form_b['num_qubits']}"))
    matcher = SequenceMatcher(a=ops_a, b=ops_b, autojunk=False)
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            lines.extend(DiffLine(" ", op) for op in ops_a[a0:a1])
        else:
            lines.extend(DiffLine("-", op) for op in ops_a[a0:a1])
            lines.extend(DiffLine("+", op) for op in ops_b[b0:b1])
    return CircuitDiff(hash_a=circuit_hash(a), hash_b=circuit_hash(b), lines=lines)
