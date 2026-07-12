"""The qontinuum / qont command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape

import qontinuum
from qontinuum.report.schema import Status, SuiteResult
from qontinuum.runner.engine import run_suite

app = typer.Typer(
    name="qontinuum",
    help="The quantum DevOps toolchain: statistical testing, cost intelligence, "
    "hardware routing, spend guards, and observability for quantum programs.",
    no_args_is_help=True,
    add_completion=True,
)
snapshot_app = typer.Typer(help="Manage golden-baseline snapshots.", no_args_is_help=True)
app.add_typer(snapshot_app, name="snapshot", rich_help_panel="State, history & spend")

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(qontinuum.__version__)
        raise typer.Exit()


@app.callback()
def _main(
    version_flag: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True,
                     help="Print the qontinuum version and exit."),
    ] = False,
) -> None:
    """qont — ship quantum code like software."""

_STYLE = {Status.PASS: "green", Status.FAIL: "red", Status.ERROR: "yellow"}
_MARK = {Status.PASS: "✓", Status.FAIL: "✗", Status.ERROR: "!"}


PathArg = Annotated[Path, typer.Argument(help="Test file or directory to search.")]
SeedOpt = Annotated[
    int | None, typer.Option(help="Simulator + transpiler seed for reproducible runs.")
]
HistoryOpt = Annotated[
    bool,
    typer.Option(
        "--history/--no-history",
        help="Append this run to .qontinuum/history.jsonl for `qont dashboard`.",
    ),
]


@app.command()
def test(
    path: PathArg = Path("."),
    seed: SeedOpt = None,
    json_out: Annotated[
        Path | None, typer.Option("--json", help="Write the suite result as JSON.")
    ] = None,
    history: HistoryOpt = True,
    cached: Annotated[
        bool,
        typer.Option("--cached", help="Reuse cached results for unchanged seeded circuits."),
    ] = False,
) -> None:
    """Discover and run quantum tests (files matching q_test_*.py)."""
    if cached and seed is None:
        console.print("[red]--cached needs --seed (unseeded runs are random on purpose)[/red]")
        raise typer.Exit(2)
    suite = _run(path, seed=seed, update_snapshots=False, use_cache=cached)
    if json_out:
        json_out.write_text(suite.model_dump_json(indent=2))
        console.print(f"[dim]wrote {json_out}[/dim]")
    if history and suite.tests:
        from qontinuum.report.history import append_history

        append_history(path, suite)
    raise typer.Exit(_exit_code(suite))


@app.command()
def cost(
    path: PathArg = Path("."),
    shots: Annotated[
        int | None,
        typer.Option(help="Override the shot count of every test for the estimate."),
    ] = None,
) -> None:
    """Estimate what running the discovered tests on real hardware would cost."""
    from rich.table import Table

    from qontinuum.cost import estimate_suite
    from qontinuum.runner.discovery import discover

    if not path.exists():
        console.print(f"[red]path not found:[/red] {path}")
        raise typer.Exit(2)
    items = discover(path)
    if not items:
        console.print("[yellow]no quantum tests found (looked for q_test_*.py)[/yellow]")
        raise typer.Exit(2)

    pairs = []
    for item in items:
        circuit = item.test.build()
        pairs.append((circuit, shots or item.test.shots))
    estimates = estimate_suite(pairs)

    total_shots = sum(s for _, s in pairs)
    table = Table(
        title=f"Estimated hardware cost — {len(pairs)} test(s), {total_shots} total shots"
    )
    table.add_column("Provider")
    table.add_column("Device")
    table.add_column("Est. cost", justify="right")
    table.add_column("Notes", style="dim")
    for est in estimates:
        if not est.feasible:
            price = "[dim]—[/dim]"
        elif est.usd is not None:
            price = f"${est.usd:,.2f}"
        else:
            price = est.units
        table.add_row(est.provider, est.display, price, est.note)
    console.print(table)
    console.print("[dim]Pre-run estimates from the public pricing catalog; not quotes.[/dim]")


@app.command(name="hash")
def hash_cmd(
    source: Annotated[Path, typer.Argument(help="QASM file to hash.")],
) -> None:
    """Print a circuit's canonical content hash."""
    from qontinuum.circuits import circuit_hash, load_circuit

    console.print(circuit_hash(load_circuit(source)))


@app.command()
def diff(
    a: Annotated[Path, typer.Argument(help="Old circuit (QASM file).")],
    b: Annotated[Path, typer.Argument(help="New circuit (QASM file).")],
) -> None:
    """Semantic diff of two circuits (register names and formatting ignored)."""
    from qontinuum.circuits import diff_circuits, load_circuit

    result = diff_circuits(load_circuit(a), load_circuit(b))
    if result.identical:
        console.print(f"[green]circuits are identical[/green] [dim]({result.hash_a})[/dim]")
        raise typer.Exit(0)
    console.print(f"[dim]--- {a}  {result.hash_a}[/dim]")
    console.print(f"[dim]+++ {b}  {result.hash_b}[/dim]")
    for line in result.lines:
        if line.tag == "-":
            console.print(f"[red]- {escape(line.text)}[/red]")
        elif line.tag == "+":
            console.print(f"[green]+ {escape(line.text)}[/green]")
        else:
            console.print(f"[dim]  {escape(line.text)}[/dim]")
    console.print(
        f"\n[bold]{result.n_added} ops added, {result.n_removed} removed[/bold]"
    )
    raise typer.Exit(1)


@app.command()
def route(
    path: PathArg = Path("."),
    optimize: Annotated[
        str,
        typer.Option(help="Ranking strategy: 'value' ($ per successful batch), "
                          "'cost', or 'fidelity'."),
    ] = "value",
) -> None:
    """Recommend which hardware should run the discovered tests."""
    from rich.table import Table

    from qontinuum.cost import estimate_suite, load_catalog, profile_circuit
    from qontinuum.router import rank, score_devices
    from qontinuum.runner.discovery import discover

    if optimize not in {"value", "cost", "fidelity"}:
        console.print(f"[red]unknown --optimize target:[/red] {optimize}")
        raise typer.Exit(2)
    if not path.exists():
        console.print(f"[red]path not found:[/red] {path}")
        raise typer.Exit(2)
    items = discover(path)
    if not items:
        console.print("[yellow]no quantum tests found (looked for q_test_*.py)[/yellow]")
        raise typer.Exit(2)

    circuits = [item.test.build() for item in items]
    pairs = [(qc, item.test.shots) for qc, item in zip(circuits, items, strict=True)]
    catalog = load_catalog()
    scores = rank(
        score_devices([profile_circuit(qc) for qc in circuits], estimate_suite(pairs), catalog),
        optimize=optimize,
    )

    table = Table(title=f"Recommended hardware — optimizing for {optimize}")
    table.add_column("#", justify="right")
    table.add_column("Provider")
    table.add_column("Device")
    table.add_column("Est. success/shot", justify="right")
    table.add_column("Est. cost", justify="right")
    table.add_column("$ / success", justify="right")
    for i, s in enumerate(scores, 1):
        if not s.feasible:
            table.add_row(str(i), s.provider, s.display, "[dim]—[/dim]",
                          "[dim]—[/dim]", f"[dim]{s.note}[/dim]")
            continue
        success = f"{s.success_prob:.1%}" if s.success_prob is not None else "?"
        price = f"${s.usd:,.2f}" if s.usd is not None else (s.units or "?")
        value = f"${s.usd_per_success:,.2f}" if s.usd_per_success is not None else "—"
        table.add_row(str(i), s.provider, s.display, success, price, value)
    console.print(table)
    console.print(
        "[dim]Success = per-shot survival from approximate vendor error rates "
        "(worst circuit in the suite); guidance, not a fidelity prediction.[/dim]"
    )


@app.command()
def run(
    path: PathArg = Path("."),
    on: Annotated[
        str,
        typer.Option("--on", help="Hardware target: 'ibm:<backend>' or 'braket:<device>'."),
    ] = "",
    max_cost: Annotated[
        float,
        typer.Option(
            "--max-cost",
            help="Budget in USD. The default $0 refuses everything: you must "
            "explicitly authorize spending.",
        ),
    ] = 0.0,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Estimate and check the budget, submit nothing.")
    ] = False,
    history: HistoryOpt = True,
) -> None:
    """Run the discovered tests on REAL hardware, guarded by a spend cap."""
    from qontinuum.hardware import HardwareError, SpendGuardError, resolve_adapter
    from qontinuum.hardware.runner import run_suite_on_hardware
    from qontinuum.report.history import append_history

    if not on:
        console.print("[red]--on is required[/red] (e.g. --on ibm:ibm_brisbane)")
        raise typer.Exit(2)
    if not path.exists():
        console.print(f"[red]path not found:[/red] {path}")
        raise typer.Exit(2)
    try:
        adapter = resolve_adapter(on)
        suite, estimated = run_suite_on_hardware(
            path, adapter, max_cost=max_cost, dry_run=dry_run
        )
    except SpendGuardError as exc:
        console.print(f"[red]spend guard:[/red] {escape(str(exc))}")
        raise typer.Exit(2) from None
    except HardwareError as exc:
        console.print(f"[red]hardware error:[/red] {escape(str(exc))}")
        raise typer.Exit(2) from None

    if dry_run:
        console.print(
            f"[green]dry run ok[/green] — estimated ${estimated:,.2f} on {adapter.target} "
            f"(within budget ${max_cost:,.2f}); nothing submitted"
        )
        raise typer.Exit(0)

    console.print(f"[dim]ran on {adapter.target}; estimated cost ${estimated:,.2f}[/dim]")
    _print_suite(suite)
    if suite.tests:
        from qontinuum.budget import record_spend

        record_spend(path, usd=estimated, target=adapter.target, tests=len(suite.tests))
    if history and suite.tests:
        append_history(path, suite, cheapest_usd=estimated)
    raise typer.Exit(_exit_code(suite))


@app.command()
def ci(
    path: PathArg = Path("."),
    seed: SeedOpt = None,
    md_out: Annotated[
        Path, typer.Option("--md", help="Where to write the markdown report.")
    ] = Path("qontinuum-report.md"),
    json_out: Annotated[
        Path | None, typer.Option("--json", help="Also write the suite result as JSON.")
    ] = None,
    history: HistoryOpt = True,
) -> None:
    """Run the suite and emit a markdown report (regressions + hardware cost)."""
    from qontinuum.cost import estimate_suite
    from qontinuum.report.markdown import render_report
    from qontinuum.runner.discovery import discover

    if not path.exists():
        console.print(f"[red]path not found:[/red] {path}")
        raise typer.Exit(2)
    suite = run_suite(path, seed=seed, update_snapshots=False)
    _print_suite(suite)

    pairs = []
    for item in discover(path):
        try:
            pairs.append((item.test.build(), item.test.shots))
        except Exception:
            continue  # already reported as an error by the runner
    estimates = estimate_suite(pairs) if pairs else []

    md_out.write_text(render_report(suite, estimates))
    console.print(f"[dim]wrote {md_out}[/dim]")
    if json_out:
        json_out.write_text(suite.model_dump_json(indent=2))
        console.print(f"[dim]wrote {json_out}[/dim]")
    if history and suite.tests:
        from qontinuum.report.history import append_history

        cheapest = min(
            (e.usd for e in estimates if e.feasible and e.usd is not None), default=None
        )
        append_history(path, suite, cheapest_usd=cheapest)
    raise typer.Exit(_exit_code(suite))


@app.command()
def dashboard(
    path: PathArg = Path("."),
    out: Annotated[
        Path, typer.Option("--out", help="Where to write the HTML dashboard.")
    ] = Path("qontinuum-dashboard.html"),
) -> None:
    """Render run history as a self-contained HTML dashboard."""
    from qontinuum.report.dashboard import render_dashboard
    from qontinuum.report.history import history_path, read_history

    records = read_history(path)
    if not records:
        console.print(
            f"[yellow]no history at {history_path(path)}; "
            "run `qont test` or `qont ci` first[/yellow]"
        )
        raise typer.Exit(2)
    out.write_text(render_dashboard(records))
    console.print(
        f"[green]wrote {out}[/green] [dim]({len(records)} runs; open it in a browser)[/dim]"
    )


@snapshot_app.command("update")
def snapshot_update(path: PathArg = Path("."), seed: SeedOpt = None) -> None:
    """Re-record golden baselines for every snapshot-enabled test."""
    suite = _run(path, seed=seed, update_snapshots=True)
    raise typer.Exit(_exit_code(suite))


@app.command()
def version() -> None:
    """Print the qontinuum version."""
    console.print(qontinuum.__version__)


def _run(
    path: Path, *, seed: int | None, update_snapshots: bool, use_cache: bool = False
) -> SuiteResult:
    if not path.exists():
        console.print(f"[red]path not found:[/red] {path}")
        raise typer.Exit(2)
    suite = run_suite(path, seed=seed, update_snapshots=update_snapshots, use_cache=use_cache)
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
            console.print(f"    [yellow]{escape(t.error)}[/yellow]")
        for c in t.checks:
            cstyle = _STYLE[c.status]
            line = f"    [{cstyle}]{_MARK[c.status]} {c.name}[/{cstyle}]"
            if c.message:
                line += f"  [dim]{escape(c.message)}[/dim]"
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


@snapshot_app.command("list")
def snapshot_list(
    path: PathArg = Path("."),
    json_mode: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List recorded golden baselines."""
    from qontinuum.cli_util import emit
    from qontinuum.runner.snapshots import SnapshotStore

    store = SnapshotStore(path if path.is_dir() else path.parent)
    rows = [
        {"test": test_id, "backend": s["backend"], "shots": s["shots"],
         "hash": s["circuit_hash"][:23] + "…", "created_at": s["created_at"]}
        for test_id, s in sorted(store._data["snapshots"].items())
    ]
    emit(rows, json_mode=json_mode, title="snapshots",
         columns=[("test", "Test"), ("backend", "Backend"), ("shots", "Shots"),
                  ("hash", "Circuit hash"), ("created_at", "Recorded")],
         right_align={"shots"})


@snapshot_app.command("show")
def snapshot_show(
    test_id: Annotated[str, typer.Argument(help="Test id from `snapshot list`.")],
    path: PathArg = Path("."),
    json_mode: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Full stored baseline for one test, including counts."""
    import json as _json

    from qontinuum.cli_util import emit_object, fail
    from qontinuum.runner.snapshots import SnapshotStore

    snap = SnapshotStore(path if path.is_dir() else path.parent).get(test_id)
    if snap is None:
        fail(f"no snapshot for {test_id!r}; run `qont snapshot list`")
    if json_mode:
        print(_json.dumps(snap, indent=2))
        return
    emit_object({k: v for k, v in snap.items() if k != "counts"},
                json_mode=False, title=test_id)
    top = sorted(snap["counts"].items(), key=lambda kv: -kv[1])[:8]
    emit_object({f"P({k})": round(v / snap["shots"], 4) for k, v in top}, json_mode=False)


@snapshot_app.command("rm")
def snapshot_rm(
    test_id: Annotated[str, typer.Argument()],
    path: PathArg = Path("."),
) -> None:
    """Delete one baseline."""
    from qontinuum.cli_util import fail
    from qontinuum.runner.snapshots import SnapshotStore

    store = SnapshotStore(path if path.is_dir() else path.parent)
    if store.get(test_id) is None:
        fail(f"no snapshot for {test_id!r}")
    del store._data["snapshots"][test_id]
    store.save()
    console.print(f"[green]removed[/green] snapshot for {test_id}")


@snapshot_app.command("prune")
def snapshot_prune(path: PathArg = Path(".")) -> None:
    """Drop baselines whose tests no longer exist."""
    from qontinuum.runner.discovery import discover
    from qontinuum.runner.snapshots import SnapshotStore

    store = SnapshotStore(path if path.is_dir() else path.parent)
    live = {item.id for item in discover(path)}
    stale = [tid for tid in store._data["snapshots"] if tid not in live]
    for tid in stale:
        del store._data["snapshots"][tid]
    if stale:
        store.save()
        for tid in stale:
            console.print(f"[green]pruned[/green] {tid}")
    else:
        console.print("[dim]no stale snapshots[/dim]")


@snapshot_app.command("verify")
def snapshot_verify(path: PathArg = Path("."), seed: SeedOpt = None) -> None:
    """Re-run snapshot tests and report drift without CI semantics."""
    suite = run_suite(path, seed=seed)
    checked = [t for t in suite.tests
               if any(c.name == "snapshot" for c in t.checks)]
    if not checked:
        console.print("[yellow]no snapshot-enabled tests found[/yellow]")
        raise typer.Exit(2)
    _print_suite(suite)


def main() -> None:  # pragma: no cover
    app()


from qontinuum import cli_groups as _cli_groups  # noqa: E402  (after app exists)

_cli_groups.register(app)


if __name__ == "__main__":  # pragma: no cover
    main()
