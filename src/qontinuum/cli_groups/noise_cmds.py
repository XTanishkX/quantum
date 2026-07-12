"""qont noise — inspect, scale, and stress-test under noise."""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import EXIT_FAILURES, JsonOpt, emit, emit_object, fail

app = typer.Typer(help="Noise models: inspect, sweep, and find headroom.", no_args_is_help=True)

PathOpt = Annotated[Path, typer.Option("--path")]
SeedOpt = Annotated[int, typer.Option()]


def _find_test(path: Path, test_id: str):
    from qontinuum.runner.discovery import discover

    matches = [i for i in discover(path)
               if i.id == test_id or i.test.name == test_id or i.id.endswith(f"::{test_id}")]
    if not matches:
        fail(f"no test matching {test_id!r} under {path}")
    return matches[0]


def _passes(item, counts) -> bool:
    from qontinuum.report.schema import Status
    from qontinuum.runner.engine import _evaluate
    from qontinuum.runner.result import RunResult

    run = RunResult(counts=counts, shots=sum(counts.values()), backend="scaled",
                    circuit_hash="")
    for check_fn in item.test.checks:
        if _evaluate(check_fn.__name__, partial(check_fn, run)).status is not Status.PASS:
            return False
    return True


@app.command("list")
def list_cmd(json_mode: JsonOpt = False) -> None:
    """Available noise sources."""
    rows = [
        {"source": "aer", "kind": "ideal", "needs": "nothing"},
        {"source": "ibm:<device>", "kind": "bundled real calibration", "needs": "[ibm] extra"},
        {"source": "ibm:<device>@live", "kind": "today's calibration", "needs": "IBM account"},
        {"source": "scaled (qont noise sweep/headroom)", "kind": "device profile x factor",
         "needs": "[ibm] extra"},
        {"source": "synthetic (qont noise inject)", "kind": "explicit error rates",
         "needs": "nothing"},
    ]
    emit(rows, json_mode=json_mode, title="noise sources",
         columns=[("source", "Source"), ("kind", "Kind"), ("needs", "Requires")])


@app.command()
def show(
    device: Annotated[str, typer.Argument(help="IBM device, e.g. manila.")],
    json_mode: JsonOpt = False,
) -> None:
    """The three-knob noise profile distilled from a device's calibration."""
    from qontinuum.noise.scaling import profile_from_device

    profile = profile_from_device(device)
    emit_object(
        {"error_1q_median": profile.error_1q, "error_2q_median": profile.error_2q,
         "error_readout_median": profile.error_readout,
         "note": "medians over the device; used by sweep/headroom scaling"},
        json_mode=json_mode,
        title=f"noise profile — {device}",
    )


@app.command()
def sweep(
    test_id: Annotated[str, typer.Argument(help="Test id or bare name.")],
    device: Annotated[str, typer.Option("--device", help="Profile source.")] = "manila",
    scales: Annotated[str, typer.Option(help="Comma-separated scale factors.")] = "0,0.5,1,1.5,2,3",
    path: PathOpt = Path("."),
    seed: SeedOpt = 7,
    json_mode: JsonOpt = False,
) -> None:
    """Run one test under progressively scaled device noise."""
    from qontinuum.noise.scaling import run_at_scale

    item = _find_test(path, test_id)
    circuit = item.test.build()
    rows = []
    for raw in scales.split(","):
        scale = float(raw)
        counts, profile = run_at_scale(circuit, device=device, scale=scale,
                                       shots=item.test.shots, seed=seed)
        rows.append({
            "scale": scale,
            "err_2q": round(profile.error_2q, 5),
            "err_readout": round(profile.error_readout, 5),
            "status": "pass" if _passes(item, counts) else "FAIL",
        })
    emit(rows, json_mode=json_mode, title=f"noise sweep — {item.id} on {device} profile",
         columns=[("scale", "Scale"), ("err_2q", "2Q err"), ("err_readout", "RO err"),
                  ("status", "Status")], right_align={"scale", "err_2q", "err_readout"})


@app.command()
def headroom(
    test_id: Annotated[str, typer.Argument(help="Test id or bare name.")],
    device: Annotated[str, typer.Option("--device")] = "manila",
    max_scale: Annotated[float, typer.Option(help="Upper search bound.")] = 8.0,
    path: PathOpt = Path("."),
    seed: SeedOpt = 7,
    json_mode: JsonOpt = False,
) -> None:
    """Load-testing for quantum: how much worse can the device get before this fails?

    Binary-searches the noise scale where the test breaks. Headroom < 1.5x
    means ordinary calibration drift can take your test down.
    """
    from qontinuum.noise.scaling import run_at_scale

    item = _find_test(path, test_id)
    circuit = item.test.build()

    def passes_at(scale: float) -> bool:
        counts, _ = run_at_scale(circuit, device=device, scale=scale,
                                 shots=item.test.shots, seed=seed)
        return _passes(item, counts)

    if not passes_at(0.0):
        fail(f"{item.id} fails even under ideal simulation — fix the test first", EXIT_FAILURES)
    if passes_at(max_scale):
        emit_object({"test": item.id, "device_profile": device,
                     "headroom_scale": f">{max_scale}",
                     "verdict": "extremely robust (or the checks are too loose)"},
                    json_mode=json_mode, title="noise headroom")
        return
    low, high = 0.0, max_scale
    for _ in range(10):
        mid = (low + high) / 2
        if passes_at(mid):
            low = mid
        else:
            high = mid
    verdict = ("fragile — normal calibration drift can break this test"
               if low < 1.5 else "healthy margin above today's device noise")
    emit_object(
        {"test": item.id, "device_profile": device, "headroom_scale": round(low, 2),
         "breaks_at_scale": round(high, 2), "verdict": verdict},
        json_mode=json_mode, title="noise headroom",
    )
    if low < 1.5:
        raise typer.Exit(EXIT_FAILURES)


@app.command()
def inject(
    test_id: Annotated[str, typer.Argument(help="Test id or bare name.")],
    error_1q: Annotated[float, typer.Option()] = 0.0,
    error_2q: Annotated[float, typer.Option()] = 0.0,
    readout: Annotated[float, typer.Option()] = 0.0,
    path: PathOpt = Path("."),
    seed: SeedOpt = 7,
    json_mode: JsonOpt = False,
) -> None:
    """Run one test under an explicit synthetic noise model."""
    from qiskit import transpile

    from qontinuum.assertions.stats import normalize_counts
    from qontinuum.noise.scaling import NoiseProfile, simulator_for

    item = _find_test(path, test_id)
    circuit = item.test.build()
    backend = simulator_for(NoiseProfile(error_1q, error_2q, readout))
    transpiled = transpile(circuit, backend, seed_transpiler=seed)
    counts = normalize_counts(
        backend.run(transpiled, shots=item.test.shots, seed_simulator=seed)
        .result().get_counts()
    )
    ok = _passes(item, counts)
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:5]
    emit_object(
        {"test": item.id, "error_1q": error_1q, "error_2q": error_2q, "readout": readout,
         **{f"P({k})": round(v / item.test.shots, 4) for k, v in top},
         "status": "pass" if ok else "FAIL"},
        json_mode=json_mode, title="synthetic noise injection",
    )
    raise typer.Exit(0 if ok else EXIT_FAILURES)
