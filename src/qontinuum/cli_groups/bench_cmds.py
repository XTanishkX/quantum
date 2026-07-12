"""qont bench — comparative benchmarks on any backend spec."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import JsonOpt, emit, emit_object, fail

app = typer.Typer(
    help="Mirror, RB-lite, and QV-style benchmarks (estimates, labeled as such).",
    no_args_is_help=True,
)

BackendOpt = Annotated[str, typer.Option("--on", help="Backend spec: aer | ibm:<device>.")]
SeedOpt = Annotated[int, typer.Option()]


@app.command()
def mirror(
    circuit_file: Annotated[Path | None, typer.Option("--circuit", help="QASM file.")] = None,
    qubits: Annotated[int, typer.Option(help="Random circuit width (no --circuit).")] = 3,
    depth: Annotated[int, typer.Option(help="Random circuit depth (no --circuit).")] = 10,
    on: BackendOpt = "aer",
    shots: Annotated[int, typer.Option()] = 2000,
    seed: SeedOpt = 7,
    json_mode: JsonOpt = False,
) -> None:
    """Mirror-circuit benchmark: run U·U†, measure survival of |0...0>."""
    from qontinuum.bench.core import mirror_survival

    if circuit_file is not None:
        from qontinuum.circuits import load_circuit

        circuit = load_circuit(circuit_file)
    else:
        from qiskit.circuit.random import random_circuit

        circuit = random_circuit(qubits, depth, seed=seed)
    survival = mirror_survival(circuit, backend_spec=on, shots=shots, seed=seed)
    emit_object(
        {"backend": on, "qubits": circuit.num_qubits, "shots": shots,
         "mirror_survival": round(survival, 4),
         "note": "1.0 = perfect; the gap is accumulated gate+readout error"},
        json_mode=json_mode, title="mirror benchmark",
    )


@app.command()
def rb(
    on: BackendOpt = "aer",
    qubits: Annotated[int, typer.Option()] = 2,
    trials: Annotated[int, typer.Option()] = 3,
    shots: Annotated[int, typer.Option()] = 1000,
    seed: SeedOpt = 7,
    json_mode: JsonOpt = False,
) -> None:
    """RB-lite: exponential decay fit over mirrored random-layer circuits."""
    from qontinuum.bench.core import rb_lite

    result = rb_lite(qubits=qubits, trials=trials, shots=shots, backend_spec=on, seed=seed)
    emit_object(
        {"backend": on, "qubits": qubits,
         "lengths": result.lengths, "survivals": result.survivals,
         "decay_p": result.decay_p, "error_per_layer": result.error_per_layer,
         "note": "mirror-RB proxy, not Clifford RB — compare, don't certify"},
        json_mode=json_mode, title="RB-lite",
    )


@app.command()
def qv(
    on: BackendOpt = "aer",
    max_qubits: Annotated[int, typer.Option()] = 4,
    trials: Annotated[int, typer.Option()] = 10,
    shots: Annotated[int, typer.Option()] = 500,
    seed: SeedOpt = 7,
    json_mode: JsonOpt = False,
) -> None:
    """Quantum-volume-style estimate (heavy-output probability per width)."""
    from qontinuum.bench.core import qv_estimate

    result = qv_estimate(max_qubits=max_qubits, trials=trials, shots=shots,
                         backend_spec=on, seed=seed)
    emit_object(
        {"backend": on, "heavy_output_probs": result.heavy_output_probs,
         "passed_widths": result.passed_widths, "failed_at_width": result.failed_width,
         "qv_estimate": result.quantum_volume_estimate,
         "note": "estimate (reduced trials, no confidence bound) — not a QV claim"},
        json_mode=json_mode, title="QV-style estimate",
    )


@app.command()
def suite(
    on: Annotated[str, typer.Option("--on", help="Comma-separated backends.")] = "aer,ibm:manila",
    seed: SeedOpt = 7,
    json_mode: JsonOpt = False,
) -> None:
    """The standard benchmark battery across several backends."""
    from qiskit.circuit.random import random_circuit

    from qontinuum.bench.core import mirror_survival, rb_lite

    rows = []
    probe = random_circuit(3, 8, seed=seed)
    for backend in [b.strip() for b in on.split(",") if b.strip()]:
        try:
            survival = mirror_survival(probe, backend_spec=backend, shots=2000, seed=seed)
            decay = rb_lite(qubits=2, trials=2, shots=800, backend_spec=backend, seed=seed)
            rows.append({"backend": backend, "mirror_survival": round(survival, 4),
                         "rb_error_per_layer": decay.error_per_layer})
        except Exception as exc:
            rows.append({"backend": backend, "mirror_survival": None,
                         "rb_error_per_layer": None, "error": str(exc)[:60]})
    emit(rows, json_mode=json_mode, title="benchmark suite (3q mirror probe + 2q RB-lite)",
         columns=[("backend", "Backend"), ("mirror_survival", "Mirror survival"),
                  ("rb_error_per_layer", "RB err/layer"), ("error", "Error")],
         right_align={"mirror_survival", "rb_error_per_layer"})


@app.command()
def compare(
    a: Annotated[str, typer.Argument(help="Backend spec A.")],
    b: Annotated[str, typer.Argument(help="Backend spec B.")],
    seed: SeedOpt = 7,
    json_mode: JsonOpt = False,
) -> None:
    """Head-to-head: which backend treats your circuits better?"""
    from qiskit.circuit.random import random_circuit

    from qontinuum.bench.core import mirror_survival

    rows = []
    for qubits, depth in [(2, 6), (3, 10), (4, 14)]:
        probe = random_circuit(qubits, depth, seed=seed + qubits)
        try:
            sa = mirror_survival(probe, backend_spec=a, shots=1500, seed=seed)
            sb = mirror_survival(probe, backend_spec=b, shots=1500, seed=seed)
        except Exception as exc:
            fail(str(exc))
        rows.append({"probe": f"{qubits}q depth {depth}",
                     a: round(sa, 4), b: round(sb, 4),
                     "winner": a if sa > sb else (b if sb > sa else "tie")})
    emit(rows, json_mode=json_mode, title=f"mirror survival — {a} vs {b}",
         columns=[("probe", "Probe"), (a, a), (b, b), ("winner", "Winner")],
         right_align={a, b})
