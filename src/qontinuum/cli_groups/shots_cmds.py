"""qont shots — the shot-count calculator engineers do on napkins today."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import EXIT_FAILURES, JsonOpt, console, emit, emit_object

app = typer.Typer(help="Statistical shot-count planning.", no_args_is_help=True)


@app.command("for-tvd")
def for_tvd(
    threshold: Annotated[float, typer.Argument(help="TVD threshold you want to assert.")],
    outcomes: Annotated[int, typer.Option(help="Support size of the expected distribution.")] = 2,
    confidence: Annotated[float, typer.Option(help="Soundness confidence.")] = 0.99,
    json_mode: JsonOpt = False,
) -> None:
    """Minimum shots so a perfect device reliably passes the given threshold."""
    from qontinuum.assertions.stats import shots_for_threshold

    shots = shots_for_threshold(outcomes, threshold, confidence)
    emit_object(
        {"tvd_threshold": threshold, "outcomes": outcomes, "confidence": confidence,
         "min_shots": shots},
        json_mode=json_mode,
    )


@app.command()
def floor(
    shots: Annotated[int, typer.Argument(help="Shots you can afford.")],
    outcomes: Annotated[int, typer.Option(help="Support size of the expected distribution.")] = 2,
    confidence: Annotated[float, typer.Option()] = 0.99,
    json_mode: JsonOpt = False,
) -> None:
    """Smallest TVD threshold that this shot count can statistically resolve."""
    from qontinuum.assertions.stats import sampling_floor

    value = sampling_floor(outcomes, shots, confidence)
    emit_object(
        {"shots": shots, "outcomes": outcomes, "confidence": confidence,
         "min_sound_tvd_threshold": round(value, 6)},
        json_mode=json_mode,
    )


@app.command()
def power(
    shots: Annotated[int, typer.Argument(help="Shots per new run.")],
    baseline_shots: Annotated[
        int, typer.Option(help="Shots in the recorded baseline (default: same).")
    ] = 0,
    alpha: Annotated[float, typer.Option()] = 0.01,
    json_mode: JsonOpt = False,
) -> None:
    """Smallest distribution drift a two-sample snapshot test can detect.

    Rule-of-thumb power analysis for a binary outcome split: detectable
    absolute probability shift ~ (z_alpha + z_80%) * sqrt(p(1-p)(1/n + 1/m)).
    """
    from scipy.stats import norm

    m = baseline_shots or shots
    z = norm.ppf(1 - alpha / 2) + norm.ppf(0.8)  # 80% power
    detectable = z * math.sqrt(0.25 * (1 / shots + 1 / m))
    emit_object(
        {"shots": shots, "baseline_shots": m, "alpha": alpha, "power": 0.8,
         "detectable_probability_shift": round(detectable, 5),
         "note": "worst case (p=0.5); smaller shifts pass unnoticed"},
        json_mode=json_mode,
    )


@app.command()
def plan(
    path: Annotated[Path, typer.Argument(help="Test file or directory.")] = Path("."),
    json_mode: JsonOpt = False,
) -> None:
    """Audit every discovered test: are its shots sound for its thresholds?

    Runs each test's checks against an ideal simulation and reports, per
    check, the threshold used vs the sampling floor at the configured shots.
    """
    from qontinuum.assertions.stats import sampling_floor
    from qontinuum.report.schema import Status
    from qontinuum.runner.engine import run_suite

    suite = run_suite(path, seed=7)
    rows, unsound = [], 0
    for test in suite.tests:
        floor_2 = sampling_floor(2, test.shots) if test.shots else None
        for check in test.checks:
            errored = check.status is Status.ERROR
            if check.threshold is None and not errored:
                continue
            sound = not errored and (
                floor_2 is None or check.threshold is None or check.threshold >= floor_2
            )
            unsound += 0 if sound else 1
            rows.append({
                "test": test.id, "check": check.name, "shots": test.shots,
                "threshold": check.threshold, "floor_at_2_outcomes": round(floor_2 or 0, 4),
                "sound": sound,
            })
    emit(rows, json_mode=json_mode, title="shot-count soundness audit",
         columns=[("test", "Test"), ("check", "Check"), ("shots", "Shots"),
                  ("threshold", "Threshold"), ("floor_at_2_outcomes", "Floor(k=2)"),
                  ("sound", "Sound")],
         right_align={"shots", "threshold", "floor_at_2_outcomes"})
    if unsound:
        console.print(f"[yellow]{unsound} check(s) look statistically unsound[/yellow]")
        raise typer.Exit(EXIT_FAILURES)
