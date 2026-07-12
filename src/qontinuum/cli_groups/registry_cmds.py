"""qont registry — named circuits with auditable version lineage."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import JsonOpt, console, emit, emit_object, fail, project_root
from qontinuum.registry import CircuitRegistry, RegistryError

app = typer.Typer(help="Named circuit lineage (git for experiments).", no_args_is_help=True)

NameArg = Annotated[str, typer.Argument(help="Registered circuit name.")]
PathOpt = Annotated[Path, typer.Option("--path", help="Project path.")]


def _registry(path: Path) -> CircuitRegistry:
    return CircuitRegistry(project_root(path))


@app.command()
def add(
    source: Annotated[Path, typer.Argument(help="Circuit file (QASM).")],
    name: Annotated[str, typer.Option("--name", help="Registry name (default: file stem).")] = "",
    note: Annotated[str, typer.Option(help="What changed in this version.")] = "",
    path: PathOpt = Path("."),
) -> None:
    """Register a circuit (new version when the canonical hash changed)."""
    from qontinuum.circuits import CircuitLoadError, circuit_hash, load_circuit

    try:
        digest = circuit_hash(load_circuit(source))
    except CircuitLoadError as exc:
        fail(str(exc))
    try:
        version = _registry(path).add(name or source.stem, circuit_hash=digest,
                                      source=str(source), note=note)
    except RegistryError as exc:
        fail(str(exc))
    console.print(f"[green]registered[/green] {name or source.stem} "
                  f"v{version['version']} [dim]{digest[:23]}…[/dim]")


@app.command("list")
def list_cmd(path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Every registered circuit with its latest version."""
    emit(_registry(path).names(), json_mode=json_mode, title="circuit registry",
         columns=[("name", "Name"), ("versions", "Versions"), ("latest_hash", "Latest hash"),
                  ("tags", "Tags"), ("updated_at", "Updated")],
         right_align={"versions"})


@app.command()
def show(name: NameArg, path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Latest version of one circuit."""
    try:
        latest = _registry(path).get(name)["versions"][-1]
    except RegistryError as exc:
        fail(str(exc))
    emit_object({"name": name, **latest}, json_mode=json_mode, title=name)


@app.command()
def log(name: NameArg, path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Hash history, newest first."""
    try:
        versions = _registry(path).log(name)
    except RegistryError as exc:
        fail(str(exc))
    emit(versions, json_mode=json_mode, title=f"lineage — {name}",
         columns=[("version", "V"), ("hash", "Hash"), ("note", "Note"), ("tags", "Tags"),
                  ("created_at", "When")], right_align={"version"})


@app.command()
def tag(
    name: NameArg,
    tag_name: Annotated[str, typer.Argument(help="Tag, e.g. production or paper-v2.")],
    version: Annotated[int | None, typer.Option(help="Version number (default: latest).")] = None,
    path: PathOpt = Path("."),
) -> None:
    """Tag a version (latest by default)."""
    try:
        target = _registry(path).tag(name, tag_name, version=version)
    except RegistryError as exc:
        fail(str(exc))
    console.print(f"[green]tagged[/green] {name} v{target['version']} as {tag_name!r}")


@app.command()
def rm(
    name: NameArg,
    path: PathOpt = Path("."),
    yes: Annotated[bool, typer.Option("--yes")] = False,
) -> None:
    """Remove a circuit and its whole lineage from the registry."""
    registry = _registry(path)
    try:
        registry.get(name)
    except RegistryError as exc:
        fail(str(exc))
    if not yes:
        typer.confirm(f"Remove {name!r} and its full lineage?", abort=True)
    registry.remove(name)
    console.print(f"[green]removed[/green] {name}")
