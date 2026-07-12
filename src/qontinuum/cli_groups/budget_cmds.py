"""qont budget — FinOps for QPU spend."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qontinuum import budget, config
from qontinuum.cli_util import JsonOpt, console, emit, emit_object, project_root

app = typer.Typer(help="Hardware spend budgets and the run ledger.", no_args_is_help=True)

PathOpt = Annotated[Path, typer.Option("--path", help="Project path.")]


@app.command("set")
def set_cmd(
    usd: Annotated[float, typer.Argument(help="Budget in USD.")],
    monthly: Annotated[bool, typer.Option("--monthly", help="Per calendar month.")] = False,
    total: Annotated[bool, typer.Option("--total", help="Lifetime cap.")] = False,
    path: PathOpt = Path("."),
) -> None:
    """Set a spend cap that `qont run` enforces before submitting anything."""
    root = project_root(path)
    key = "budget.monthly_usd" if monthly or not total else "budget.total_usd"
    config.set_value(root, key, str(usd))
    console.print(f"[green]set[/green] {key} = ${usd:,.2f}")


@app.command()
def show(path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Current caps."""
    root = project_root(path)
    cfg = config.effective(root)
    emit_object(
        {"monthly_usd": cfg.get("budget.monthly_usd"), "total_usd": cfg.get("budget.total_usd")},
        json_mode=json_mode,
        title="budget caps",
    )


@app.command("status")
def status_cmd(path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Spend vs caps, from the run ledger."""
    emit_object(budget.status(project_root(path)), json_mode=json_mode, title="budget status")


@app.command()
def ledger(
    path: PathOpt = Path("."),
    limit: Annotated[int, typer.Option()] = 20,
    json_mode: JsonOpt = False,
) -> None:
    """Recorded hardware-run spend entries."""
    entries = budget.read_ledger(project_root(path))[-limit:]
    emit(entries, json_mode=json_mode, title="spend ledger (estimates at submission time)",
         columns=[("at", "When"), ("target", "Target"), ("tests", "Tests"), ("usd", "USD")],
         right_align={"tests", "usd"})


@app.command()
def forecast(path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Project this month's spend from the current run cadence."""
    result = budget.forecast(project_root(path))
    if result is None:
        console.print("[dim]no hardware runs recorded this month — nothing to project[/dim]")
        return
    emit_object(result, json_mode=json_mode, title="spend forecast (naive linear)")


@app.command()
def reset(
    path: PathOpt = Path("."),
    yes: Annotated[bool, typer.Option("--yes", help="Skip confirmation.")] = False,
) -> None:
    """Clear the spend ledger (caps stay configured)."""
    root = project_root(path)
    target = budget.ledger_path(root)
    if not target.is_file():
        console.print("[dim]ledger is already empty[/dim]")
        return
    if not yes:
        typer.confirm(f"Delete {target}?", abort=True)
    target.unlink()
    console.print("[green]ledger cleared[/green]")
