"""The qontinuum / qont command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

import qontinuum
from qontinuum.report.schema import Status, SuiteResult
from qontinuum.runner.engine import run_suite

app = typer.Typer(
    name="qontinuum",
    help="CI/CD, noise-aware regression testing, and cost intelligence for quantum programs.",
    no_args_is_help=True,
    add_completion=False,
)
snapshot_app = typer.Typer(help="Manage golden-baseline snapshots.", no_args_is_help=True)
app.add_typer(snapshot_app, name="snapshot")

console = Console()

_STYLE = {Status.PASS: "green", Status.FAIL: "red", Status.ERROR: "yellow"}
_MARK = {Status.PASS: "✓", Status.FAIL: "✗", Status.ERROR: "!"}


PathArg = Annotated[Path, typer.Argument(help="Test file or directory to search.")]
SeedOpt = Annotated[
    int | None, typer.Option(help="Simulator + transpiler seed for reproducible runs.")
]


@app.command()
def test(
    path: PathArg = Path("."),
    seed: SeedOpt = None,
    json_out: Annotated[
        Path | None, typer.Option("--json", help="Write the suite result as JSON.")
    ] = None,
) -> None:
    """Discover and run quantum tests (files matching q_test_*.py)."""
    suite = _run(path, seed=seed, update_snapshots=False)
    if json_out:
        json_out.write_text(suite.model_dump_json(indent=2))
        console.print(f"[dim]wrote {json_out}[/dim]")
    raise typer.Exit(_exit_code(suite))


@snapshot_app.command("update")
def snapshot_update(path: PathArg = Path("."), seed: SeedOpt = None) -> None:
    """Re-record golden baselines for every snapshot-enabled test."""
    suite = _run(path, seed=seed, update_snapshots=True)
    raise typer.Exit(_exit_code(suite))


@app.command()
def version() -> None:
    """Print the qontinuum version."""
    console.print(qontinuum.__version__)


def _run(path: Path, *, seed: int | None, update_snapshots: bool) -> SuiteResult:
    if not path.exists():
        console.print(f"[red]path not found:[/red] {path}")
        raise typer.Exit(2)
    suite = run_suite(path, seed=seed, update_snapshots=update_snapshots)
    _print_suite(suite)
    return suite


def _print_suite(suite: SuiteResult) -> None:
    if not suite.tests:
        console.print("[yellow]no quantum tests found (looked for q_test_*.py)[/yellow]")
        return
    for t in suite.tests:
        style = _STYLE[t.status]
        header = f"[{style}]{_MARK[t.status]}[/{style}] [bold]{t.id}[/bold]"
        meta = f"[dim]{t.backend}, {t.shots} shots, {t.duration_ms:.0f} ms[/dim]"
        console.print(f"{header}  {meta}")
        if t.error:
            console.print(f"    [yellow]{t.error}[/yellow]")
        for c in t.checks:
            cstyle = _STYLE[c.status]
            line = f"    [{cstyle}]{_MARK[c.status]} {c.name}[/{cstyle}]"
            if c.message:
                line += f"  [dim]{c.message}[/dim]"
            console.print(line)
    tally = suite.tally()
    summary = f"{tally['pass']} passed, {tally['fail']} failed, {tally['error']} errors"
    console.print(f"\n[bold]{summary}[/bold] [dim](seed={suite.seed})[/dim]")


def _exit_code(suite: SuiteResult) -> int:
    if suite.status is Status.ERROR:
        return 2
    if suite.status is Status.FAIL:
        return 1
    return 0


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
