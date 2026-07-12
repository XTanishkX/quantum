"""Flat power tools: mock, fuzz, explain, and the watch group."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_groups import PANEL_ANALYSIS, PANEL_HARDWARE
from qontinuum.cli_util import (
    EXIT_FAILURES,
    JsonOpt,
    console,
    emit,
    emit_object,
    fail,
)

watch_app = typer.Typer(help="Re-run on change / poll live calibration.", no_args_is_help=True)


def register_flat(app: typer.Typer) -> None:
    app.command(rich_help_panel=PANEL_ANALYSIS)(mock)
    app.command(rich_help_panel=PANEL_ANALYSIS)(fuzz)
    app.command(rich_help_panel=PANEL_ANALYSIS)(explain)
    app.add_typer(watch_app, name="watch", rich_help_panel=PANEL_HARDWARE)


def mock(
    qubits: Annotated[int, typer.Option(help="Qubit count.")] = 2,
    state: Annotated[str, typer.Option(help="bell | ghz | uniform | zeros")] = "bell",
    shots: Annotated[int, typer.Option()] = 1000,
    seed: Annotated[int, typer.Option()] = 7,
    noise: Annotated[float, typer.Option(help="Flip each bit with this probability.")] = 0.0,
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    """Generate synthetic measurement counts (test fixtures, demos, docs)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    n = qubits
    if state == "bell" and n >= 2:
        basis = ["0" * n, "1" * n][:2]
        draws = rng.choice(2, size=shots)
        outcomes = [basis[d] for d in draws]
    elif state == "ghz":
        draws = rng.choice(2, size=shots)
        outcomes = ["0" * n if d == 0 else "1" * n for d in draws]
    elif state == "uniform":
        draws = rng.integers(0, 2**n, size=shots)
        outcomes = [format(d, f"0{n}b") for d in draws]
    elif state == "zeros":
        outcomes = ["0" * n] * shots
    else:
        fail(f"unknown state {state!r}; use bell, ghz, uniform, or zeros")
    if noise > 0:
        flips = rng.random((shots, n)) < noise
        outcomes = [
            "".join("1" if (bit == "0") == flip else "0"
                    for bit, flip in zip(outcome, row, strict=True))
            for outcome, row in zip(outcomes, flips, strict=True)
        ]
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome] = counts.get(outcome, 0) + 1
    text = json.dumps(dict(sorted(counts.items())), indent=2)
    if out:
        out.write_text(text)
        console.print(f"[green]wrote[/green] {out} [dim]({state}, {shots} shots)[/dim]")
    else:
        print(text)


def fuzz(
    path: Annotated[Path, typer.Argument(help="Test file or directory.")] = Path("."),
    trials: Annotated[int, typer.Option(help="Independent seeded reruns.")] = 30,
    min_pass_rate: Annotated[float, typer.Option(help="Fail below this empirical rate.")] = 0.99,
    base_seed: Annotated[int, typer.Option()] = 1000,
    json_mode: JsonOpt = False,
) -> None:
    """Flakiness hunter: rerun the suite under a seed sweep, estimate pass rates.

    A test that passes once might still fail 3% of the time in CI. This
    measures that number empirically, with a Wilson confidence interval.
    """
    from qontinuum.report.schema import Status
    from qontinuum.runner.engine import run_suite

    passes: dict[str, int] = {}
    total: dict[str, int] = {}
    for trial in range(trials):
        suite = run_suite(path, seed=base_seed + trial)
        for test in suite.tests:
            total[test.id] = total.get(test.id, 0) + 1
            if test.status is Status.PASS:
                passes[test.id] = passes.get(test.id, 0) + 1
    if not total:
        fail("no quantum tests found")
    rows, flaky = [], 0
    for test_id in sorted(total):
        n, k = total[test_id], passes.get(test_id, 0)
        rate = k / n
        low, high = _wilson(k, n)
        ok = rate >= min_pass_rate
        flaky += 0 if ok else 1
        rows.append({"test": test_id, "trials": n, "pass_rate": f"{rate:.1%}",
                     "wilson_95": f"[{low:.1%}, {high:.1%}]", "ok": ok})
    emit(rows, json_mode=json_mode, title=f"flakiness fuzz — {trials} seeded trials",
         columns=[("test", "Test"), ("trials", "Trials"), ("pass_rate", "Pass rate"),
                  ("wilson_95", "95% CI"), ("ok", "OK")],
         right_align={"trials", "pass_rate"})
    if flaky:
        console.print(f"[yellow]{flaky} test(s) below --min-pass-rate {min_pass_rate:.0%}: "
                      "widen thresholds or raise shots (see `qont shots plan`)[/yellow]")
        raise typer.Exit(EXIT_FAILURES)


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def explain(
    test_id: Annotated[str, typer.Argument(help="Test id or bare test name.")],
    path: Annotated[Path, typer.Option("--path")] = Path("."),
    seed: Annotated[int | None, typer.Option()] = None,
    json_mode: JsonOpt = False,
) -> None:
    """Failure forensics: which outcomes drove a failing check, and why.

    Re-runs one test, decomposes the statistic outcome-by-outcome, and maps
    the error signature (odd-parity leakage vs distribution skew) to the
    likely physical cause and a concrete fix.
    """
    from qontinuum.assertions.stats import to_probs
    from qontinuum.report.schema import Status
    from qontinuum.runner.backends import execute
    from qontinuum.runner.discovery import discover

    matches = [i for i in discover(path)
               if i.id == test_id or i.test.name == test_id or i.id.endswith(f"::{test_id}")]
    if not matches:
        fail(f"no test matching {test_id!r} under {path}")
    item = matches[0]
    circuit = item.test.build()
    run = execute(circuit, shots=item.test.shots, backend_spec=item.test.backend, seed=seed)

    from functools import partial

    from qontinuum.runner.engine import _evaluate

    findings: list[dict] = []
    for check_fn in item.test.checks:
        result = _evaluate(check_fn.__name__, partial(check_fn, run))
        if result.status is Status.PASS:
            continue
        findings.append({"check": result.name, "message": result.message,
                         "statistic": result.statistic, "threshold": result.threshold})

    probs = to_probs(run.counts)
    n = circuit.num_qubits
    odd_parity = sum(p for outcome, p in probs.items()
                     if outcome.count("1") % 2 == 1) if n >= 2 else 0.0
    top = sorted(probs.items(), key=lambda kv: -kv[1])[:6]

    diagnosis: list[str] = []
    if not findings:
        diagnosis.append("all checks pass on this rerun — the earlier failure may be "
                         "statistical flakiness; quantify it with `qont fuzz`")
    else:
        if odd_parity > 0.05:
            diagnosis.append(
                f"odd-parity mass is {odd_parity:.1%} — signature of readout error or "
                "decoherence, not a logic bug; if running under a noise model this is "
                "expected: loosen the threshold or use unexpected_tolerance"
            )
        dominant = top[0]
        if dominant[1] > 0.9:
            diagnosis.append(
                f"one outcome ({dominant[0]}) dominates at {dominant[1]:.1%} — check for a "
                "missing Hadamard/entangling gate or measuring before the interesting part"
            )
        if any(f["threshold"] is not None and f["statistic"] is not None
               and f["statistic"] < 1.5 * f["threshold"] for f in findings):
            diagnosis.append(
                "the statistic is within 1.5x of the threshold — borderline; consider more "
                "shots (see `qont shots for-tvd`) before concluding a regression"
            )
        if not diagnosis:
            diagnosis.append("distribution shape changed materially — inspect with "
                             "`qont circuit diff` against the last known-good version")

    emit_object(
        {
            "test": item.id,
            "backend": item.test.backend,
            "shots": item.test.shots,
            "failing_checks": [f["check"] for f in findings] or None,
            **{f"P({k})": round(p, 4) for k, p in top},
            "odd_parity_mass": round(odd_parity, 4),
            "diagnosis": diagnosis,
        },
        json_mode=json_mode,
        title=f"explain {item.id}",
    )
    raise typer.Exit(EXIT_FAILURES if findings else 0)


@watch_app.command("test")
def watch_test(
    path: Annotated[Path, typer.Argument()] = Path("."),
    interval: Annotated[float, typer.Option(help="Poll interval (seconds).")] = 1.0,
    seed: Annotated[int | None, typer.Option()] = None,
) -> None:
    """Re-run the suite whenever a q_test file changes (Ctrl-C to stop)."""
    from qontinuum.runner.discovery import find_test_files

    def fingerprint() -> dict[str, float]:
        return {str(f): f.stat().st_mtime for f in find_test_files(path)}

    last: dict[str, float] = {}
    console.print(f"[dim]watching {path} for q_test_*.py changes — Ctrl-C to stop[/dim]")
    try:
        while True:
            current = fingerprint()
            if current != last:
                last = current
                console.rule(time.strftime("%H:%M:%S"))
                from qontinuum.cli import _print_suite
                from qontinuum.runner.engine import run_suite

                _print_suite(run_suite(path, seed=seed))
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]stopped[/dim]")


@watch_app.command("device")
def watch_device(
    device: Annotated[str, typer.Argument(help="IBM device, e.g. brisbane (uses @live).")],
    interval: Annotated[float, typer.Option(help="Poll interval (seconds).")] = 300.0,
    alert_pct: Annotated[float, typer.Option(help="Alert when a median moves this much %.")] = 10.0,
) -> None:
    """Poll live calibration and alert on drift (needs a saved IBM account)."""
    from qontinuum.cli_groups.device_cmds import _calibration_summary

    name = device.partition("@")[0]
    baseline = _calibration_summary(f"{name}@live")
    console.print(f"[dim]baseline {name}: {baseline} — polling every {interval:.0f}s[/dim]")
    try:
        while True:
            time.sleep(interval)
            current = _calibration_summary(f"{name}@live")
            for metric, base in baseline.items():
                now = current.get(metric)
                if base and now is not None:
                    change = (now - base) / base * 100
                    if abs(change) >= alert_pct:
                        console.print(f"[yellow]{time.strftime('%H:%M:%S')} {metric}: "
                                      f"{base} -> {now} ({change:+.1f}%)[/yellow]")
    except KeyboardInterrupt:
        console.print("\n[dim]stopped[/dim]")
