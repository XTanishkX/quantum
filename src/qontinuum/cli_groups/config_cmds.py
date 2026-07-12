"""qont config — git-config-style project configuration."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from qontinuum import config
from qontinuum.cli_util import EXIT_USAGE, console, emit, fail, project_root

app = typer.Typer(help="Project configuration (.qontinuum/config.toml).", no_args_is_help=True)

KeyArg = Annotated[str, typer.Argument(help="Dotted key, e.g. defaults.seed")]


def _root() -> Path:
    return project_root()


@app.command("get")
def get_cmd(key: KeyArg) -> None:
    """Print one config value (built-in default when unset)."""
    try:
        value = config.get(_root(), key)
    except config.ConfigError as exc:
        fail(str(exc))
    print(json.dumps(value))


@app.command("set")
def set_cmd(
    key: KeyArg,
    value: Annotated[
        str, typer.Argument(help='Value (JSON or plain string), e.g. 42 or \'["Q003"]\'')
    ],
) -> None:
    """Set a config value."""
    try:
        parsed = config.set_value(_root(), key, value)
    except config.ConfigError as exc:
        fail(str(exc))
    console.print(f"[green]set[/green] {key} = {json.dumps(parsed)}")


@app.command()
def unset(key: KeyArg) -> None:
    """Remove a key (reverts to the built-in default)."""
    try:
        existed = config.unset(_root(), key)
    except config.ConfigError as exc:
        fail(str(exc))
    console.print(f"[green]unset[/green] {key}" if existed else f"[dim]{key} was not set[/dim]")


@app.command("list")
def list_cmd(json_mode: Annotated[bool, typer.Option("--json")] = False) -> None:
    """Show every known key: effective value, source, and description."""
    root = _root()
    try:
        stored = config.load(root)
    except config.ConfigError as exc:
        fail(str(exc))
    rows = []
    for key, (default, description) in sorted(config.KNOWN_KEYS.items()):
        rows.append(
            {
                "key": key,
                "value": stored.get(key, default),
                "source": "project" if key in stored else "default",
                "description": description,
            }
        )
    emit(rows, json_mode=json_mode, title=f"config — {config.config_path(root)}",
         columns=[("key", "Key"), ("value", "Value"), ("source", "Source"),
                  ("description", "Description")])


@app.command()
def path() -> None:
    """Print the config file path."""
    print(config.config_path(_root()))


@app.command()
def edit() -> None:
    """Open the config file in $EDITOR."""
    target = config.config_path(_root())
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Qontinuum project configuration\n")
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        fail("no $EDITOR set; edit the file directly: " + str(target), EXIT_USAGE)
    subprocess.run([editor, str(target)], check=False)
