"""Shared CLI plumbing: table/JSON rendering, counts IO, exit conventions.

Every read command supports ``--json`` and renders through :func:`emit` so the
human table and the machine output always carry the same data. Exit codes are
uniform across the CLI: 0 ok · 1 findings/failures · 2 usage-or-config error ·
3 guard refusal (spend/budget).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

console = Console()

EXIT_OK = 0
EXIT_FAILURES = 1
EXIT_USAGE = 2
EXIT_GUARD = 3

JsonOpt = Annotated[bool, typer.Option("--json", help="Emit machine-readable JSON.")]


def fail(message: str, code: int = EXIT_USAGE) -> NoReturn:
    console.print(f"[red]error:[/red] {escape(message)}")
    raise typer.Exit(code)


def emit(
    rows: list[dict[str, Any]],
    *,
    json_mode: bool,
    title: str = "",
    columns: list[tuple[str, str]] | None = None,
    right_align: set[str] | None = None,
) -> None:
    """Render rows as a rich table, or as JSON when ``--json`` was passed.

    ``columns`` is an ordered list of ``(key, header)``; defaults to the keys
    of the first row. JSON mode always emits the full row dicts.
    """
    if json_mode:
        print(json.dumps(rows, indent=2, default=str))
        return
    if not rows:
        console.print("[dim]nothing to show[/dim]")
        return
    cols = columns or [(k, k) for k in rows[0]]
    table = Table(title=title or None)
    right = right_align or set()
    for key, header in cols:
        table.add_column(header, justify="right" if key in right else "left")
    for row in rows:
        table.add_row(*(_cell(row.get(key)) for key, _ in cols))
    console.print(table)


def emit_object(obj: dict[str, Any], *, json_mode: bool, title: str = "") -> None:
    """Render a single object as a key/value listing or JSON."""
    if json_mode:
        print(json.dumps(obj, indent=2, default=str))
        return
    if title:
        console.print(f"[bold]{escape(title)}[/bold]")
    width = max((len(str(k)) for k in obj), default=0)
    for key, value in obj.items():
        console.print(f"  [dim]{str(key).ljust(width)}[/dim]  {_cell(value)}")


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:,.4g}"
    if isinstance(value, (list, dict)):
        return escape(json.dumps(value, ensure_ascii=False))
    return escape(str(value))


def read_counts_file(path: Path) -> dict[str, int]:
    """Load measurement counts from a JSON file.

    Accepts a flat ``{"00": 512, ...}`` mapping, an object with a ``counts``
    key, or a suite-result JSON containing exactly one test.
    """
    if not path.is_file():
        fail(f"no such counts file: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")
    if isinstance(data, dict) and "counts" in data and isinstance(data["counts"], dict):
        data = data["counts"]
    elif isinstance(data, dict) and "tests" in data:
        tests = [t for t in data["tests"] if t.get("counts")]
        if len(tests) != 1:
            fail(f"{path} is a suite result with {len(tests)} tests; pass a single-counts file")
        data = tests[0]["counts"]
    if not isinstance(data, dict) or not all(
        isinstance(v, int) and isinstance(k, str) for k, v in data.items()
    ):
        fail(f"{path} does not contain string->int measurement counts")
    return data


def project_root(path: Path | None = None) -> Path:
    """Walk upward to the nearest directory carrying .qontinuum/ or .git/."""
    current = (path or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".qontinuum").is_dir() or (candidate / ".git").is_dir():
            return candidate
    return current
