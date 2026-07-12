"""qont circuit — inspection, conversion, and generation plumbing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import EXIT_FAILURES, JsonOpt, console, emit_object, fail

app = typer.Typer(help="Inspect, convert, and generate circuits.", no_args_is_help=True)

SourceArg = Annotated[Path, typer.Argument(help="Circuit file (QASM 2 or 3).")]


def _load(path: Path):
    from qontinuum.circuits import CircuitLoadError, load_circuit

    try:
        return load_circuit(path)
    except CircuitLoadError as exc:
        fail(str(exc))


@app.command()
def show(source: SourceArg) -> None:
    """Draw the circuit as unicode art."""
    console.print(str(_load(source).draw(output="text", fold=100)))


@app.command("stats")
def stats_cmd(source: SourceArg, json_mode: JsonOpt = False) -> None:
    """Gate counts, depth, SPAM profile, and content hash."""
    from qontinuum.circuits import circuit_hash
    from qontinuum.cost import profile_circuit

    circuit = _load(source)
    profile = profile_circuit(circuit)
    emit_object(
        {
            "qubits": profile.num_qubits,
            "clbits": circuit.num_clbits,
            "depth": profile.depth,
            "gates_1q": profile.n_1q_gates,
            "gates_2q": profile.n_2q_gates,
            "gates_2q_effective": profile.n_2q_effective,
            "measurements": profile.n_measurements,
            "spam_ops": profile.n_spam,
            "hash": circuit_hash(circuit),
        },
        json_mode=json_mode,
        title=str(source),
    )


@app.command()
def canon(source: SourceArg) -> None:
    """Print the versioned canonical form (what the content hash covers)."""
    from qontinuum.circuits import canonical_form

    print(json.dumps(canonical_form(_load(source)), indent=2))


@app.command("hash")
def hash_cmd(source: SourceArg) -> None:
    """Print the circuit's canonical content hash."""
    from qontinuum.circuits import circuit_hash

    print(circuit_hash(_load(source)))


@app.command("diff")
def diff_cmd(a: SourceArg, b: SourceArg) -> None:
    """Semantic diff (same engine as top-level `qont diff`)."""
    from qontinuum.cli import diff as top_diff

    top_diff(a, b)


@app.command()
def convert(
    source: SourceArg,
    to: Annotated[str, typer.Option("--to", help="Target dialect: qasm2 | qasm3")] = "qasm3",
    out: Annotated[
        Path | None, typer.Option("--out", help="Write to file instead of stdout.")
    ] = None,
) -> None:
    """Convert between OpenQASM dialects (also accepts Cirq/PennyLane via API)."""
    circuit = _load(source)
    if to == "qasm3":
        from qiskit import qasm3

        text = qasm3.dumps(circuit)
    elif to == "qasm2":
        from qiskit import qasm2

        try:
            text = qasm2.dumps(circuit)
        except Exception as exc:
            fail(f"cannot express this circuit in QASM 2: {exc}")
    else:
        fail(f"unknown dialect {to!r}; use qasm2 or qasm3")
    if out:
        out.write_text(text)
        console.print(f"[green]wrote[/green] {out}")
    else:
        print(text)


@app.command()
def transpile(
    source: SourceArg,
    target: Annotated[str, typer.Option("--for", help="Target device, e.g. ibm:manila.")],
    json_mode: JsonOpt = False,
) -> None:
    """Show what the device will actually run: depth/gate deltas after targeting."""
    from qiskit import transpile as qk_transpile

    from qontinuum.cost import profile_circuit
    from qontinuum.runner.backends import BackendSpecError, resolve_backend

    circuit = _load(source)
    try:
        backend = resolve_backend(target)
    except (BackendSpecError, Exception) as exc:
        fail(f"cannot resolve target {target!r}: {exc}")
    before = profile_circuit(circuit)
    compiled = qk_transpile(circuit, backend, optimization_level=1, seed_transpiler=7)
    after = profile_circuit(compiled)
    growth = (after.n_2q_effective / before.n_2q_effective) if before.n_2q_effective else 1.0
    emit_object(
        {
            "target": target,
            "depth": f"{before.depth} -> {after.depth}",
            "gates_1q": f"{before.n_1q_gates} -> {after.n_1q_gates}",
            "gates_2q": f"{before.n_2q_effective} -> {after.n_2q_effective}",
            "two_qubit_growth": f"{growth:.2f}x",
            "note": "routing/SWAP overhead the abstract circuit hides",
        },
        json_mode=json_mode,
        title=f"transpile {source} for {target}",
    )


@app.command()
def equiv(a: SourceArg, b: SourceArg, json_mode: JsonOpt = False) -> None:
    """True unitary equivalence via statevector (up to global phase, <=12 qubits).

    Stronger than `qont diff` (structural): rz(pi);rz(pi) == rz(2pi) here.
    """
    import numpy as np
    from qiskit.quantum_info import Statevector

    ca = _load(a).remove_final_measurements(inplace=False)
    cb = _load(b).remove_final_measurements(inplace=False)
    if ca.num_qubits != cb.num_qubits:
        console.print("[red]not equivalent[/red] (different qubit counts)")
        raise typer.Exit(EXIT_FAILURES)
    if ca.num_qubits > 12:
        fail("equivalence check is limited to 12 qubits (statevector memory)")
    overlap = abs(np.vdot(Statevector(ca).data, Statevector(cb).data))
    equivalent = bool(overlap > 1 - 1e-9)
    emit_object(
        {"equivalent": equivalent, "state_overlap": round(float(overlap), 12)},
        json_mode=json_mode,
        title="unitary equivalence (on |0...0>, up to global phase)",
    )
    raise typer.Exit(0 if equivalent else EXIT_FAILURES)


@app.command()
def mirror(
    source: SourceArg,
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    """Emit the mirror-benchmark circuit U·U†: ideal outcome is all zeros.

    Run it on hardware or a noise model — any weight on other outcomes is
    pure accumulated error, making it a self-verifying benchmark.
    """
    from qiskit import qasm3

    circuit = _load(source).remove_final_measurements(inplace=False)
    mirrored = circuit.compose(circuit.inverse())
    mirrored.measure_all()
    text = qasm3.dumps(mirrored)
    if out:
        out.write_text(text)
        console.print(f"[green]wrote[/green] {out} [dim](expect all-zeros outcome)[/dim]")
    else:
        print(text)


@app.command()
def random(
    qubits: Annotated[int, typer.Option(help="Qubit count.")] = 4,
    depth: Annotated[int, typer.Option(help="Circuit depth.")] = 8,
    seed: Annotated[int, typer.Option(help="Reproducibility seed.")] = 7,
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    """Generate a reproducible random circuit (fuzzing / benchmarking input)."""
    from qiskit import qasm3
    from qiskit.circuit.random import random_circuit

    circuit = random_circuit(qubits, depth, measure=True, seed=seed)
    text = qasm3.dumps(circuit)
    if out:
        out.write_text(text)
        console.print(f"[green]wrote[/green] {out}")
    else:
        print(text)
