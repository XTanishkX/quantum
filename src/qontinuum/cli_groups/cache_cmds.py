"""qont cache — manage the content-addressed simulation result cache."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qontinuum import cache
from qontinuum.cli_util import JsonOpt, console, emit, emit_object

app = typer.Typer(help="Simulation result cache (seeded runs only).", no_args_is_help=True)

PathOpt = Annotated[Path, typer.Option("--path", help="Project path.")]


@app.command("stats")
def stats_cmd(path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Cache size and entry count."""
    entries = cache.entries(path)
    emit_object(
        {
            "entries": len(entries),
            "total_bytes": sum(e["bytes"] for e in entries),
            "oldest": min((e["created_at"] for e in entries if e["created_at"]), default=None),
            "newest": max((e["created_at"] for e in entries if e["created_at"]), default=None),
        },
        json_mode=json_mode,
        title="result cache",
    )


@app.command()
def ls(path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """List cached results."""
    emit(cache.entries(path), json_mode=json_mode, title="cached results",
         columns=[("key", "Key"), ("test", "Test"), ("shots", "Shots"),
                  ("created_at", "Created"), ("bytes", "Bytes")],
         right_align={"shots", "bytes"})


@app.command()
def clear(path: PathOpt = Path(".")) -> None:
    """Delete every cached result."""
    console.print(f"[green]removed {cache.clear(path)} entries[/green]")


@app.command()
def gc(
    path: PathOpt = Path("."),
    max_age_days: Annotated[float, typer.Option(help="Delete entries older than this.")] = 30,
) -> None:
    """Garbage-collect old cache entries."""
    console.print(f"[green]removed {cache.gc(path, max_age_days=max_age_days)} entries[/green]")
