"""qont pack — reproducibility bundles you can hand to a reviewer."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import EXIT_FAILURES, JsonOpt, console, emit, emit_object, fail
from qontinuum.pack import PackError, create_pack, inspect_pack, verify_pack

app = typer.Typer(help="Create and verify reproducibility bundles.", no_args_is_help=True)

BundleArg = Annotated[Path, typer.Argument(help="Pack file (.tar.gz).")]


@app.command()
def create(
    path: Annotated[Path, typer.Argument(help="Test file or directory.")] = Path("."),
    out: Annotated[Path, typer.Option("--out")] = Path("qontinuum-pack.tar.gz"),
    seed: Annotated[int, typer.Option()] = 42,
) -> None:
    """Bundle the suite, baselines, seeded results, and environment lock."""
    try:
        manifest = create_pack(path, out, seed=seed)
    except PackError as exc:
        fail(str(exc))
    console.print(
        f"[green]wrote[/green] {out} "
        f"[dim]({len(manifest['files'])} files, seed {seed}, "
        f"qiskit {manifest['environment'].get('qiskit')})[/dim]"
    )


@app.command()
def inspect(bundle: BundleArg, json_mode: JsonOpt = False) -> None:
    """Show a pack's manifest: environment, files, suite summary."""
    try:
        manifest = inspect_pack(bundle)
    except (PackError, FileNotFoundError, Exception) as exc:
        fail(str(exc))
    tests = manifest["suite"]["tests"]
    emit_object(
        {
            "created_at": manifest["created_at"],
            "seed": manifest["seed"],
            "tests": len(tests),
            "files": len(manifest["files"]),
            "python": manifest["environment"].get("python"),
            "qiskit": manifest["environment"].get("qiskit"),
            "catalog_verified": manifest["catalog_verified"],
        },
        json_mode=json_mode,
        title=str(bundle),
    )


@app.command()
def verify(
    bundle: BundleArg,
    alpha: Annotated[float, typer.Option(help="Two-sample significance level.")] = 0.01,
    json_mode: JsonOpt = False,
) -> None:
    """Re-run the packed suite in THIS environment; do the results reproduce?"""
    try:
        results = verify_pack(bundle, alpha=alpha)
    except (PackError, Exception) as exc:
        fail(str(exc))
    emit(results, json_mode=json_mode, title=f"reproduction check — {bundle}",
         columns=[("test", "Test"), ("p_value", "p-value"), ("verdict", "Verdict")],
         right_align={"p_value"})
    bad = [r for r in results if r.get("verdict") != "reproduces"]
    if bad:
        console.print(f"[yellow]{len(bad)} test(s) did not cleanly reproduce — "
                      "compare environments with `qont env diff`[/yellow]")
        raise typer.Exit(EXIT_FAILURES)
    console.print("[green]every packed result reproduces in this environment[/green]")
