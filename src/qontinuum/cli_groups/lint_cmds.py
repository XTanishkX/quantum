"""qont lint — ruff for quantum test suites."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import EXIT_FAILURES, JsonOpt, console, emit, fail, project_root

app = typer.Typer(
    help="Static + probe-based checks for quantum test suites (rules Q001-Q009). "
    "Bare `qont lint` scans the current directory; `qont lint check <path>` scans "
    "elsewhere.",
    invoke_without_command=True,
    no_args_is_help=False,
)

SelectOpt = Annotated[str | None, typer.Option(help="Only these codes, e.g. Q001,Q006")]
IgnoreOpt = Annotated[str | None, typer.Option(help="Skip these codes.")]


def _scan(path: Path, select: str | None, ignore: str | None, json_mode: bool) -> None:
    from qontinuum import config
    from qontinuum.lint.engine import lint_path

    ignore_set = set(filter(None, (ignore or "").split(",")))
    ignore_set |= set(config.effective(project_root(path)).get("lint.ignore") or [])
    select_set = set(filter(None, (select or "").split(","))) or None
    try:
        findings = lint_path(path, select=select_set, ignore=ignore_set or None)
    except ValueError as exc:
        fail(str(exc))
    rows = [
        {"code": f.code, "severity": f.severity, "test": f.test_id, "message": f.message}
        for f in findings
    ]
    emit(rows, json_mode=json_mode, title="qont lint",
         columns=[("code", "Rule"), ("severity", "Severity"), ("test", "Test"),
                  ("message", "Message")])
    if findings:
        errors = sum(1 for f in findings if f.severity == "error")
        if not json_mode:
            console.print(f"[bold]{len(findings)} finding(s)[/bold] "
                          f"({errors} errors) — `qont lint explain <code>` for details")
        raise typer.Exit(EXIT_FAILURES)
    if not json_mode:
        console.print("[green]no findings[/green]")


@app.callback()
def lint(
    ctx: typer.Context,
    select: SelectOpt = None,
    ignore: IgnoreOpt = None,
    json_mode: JsonOpt = False,
) -> None:
    """Scan the current directory when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return
    _scan(Path("."), select, ignore, json_mode)


@app.command()
def check(
    path: Annotated[Path, typer.Argument(help="Test file or directory.")] = Path("."),
    select: SelectOpt = None,
    ignore: IgnoreOpt = None,
    json_mode: JsonOpt = False,
) -> None:
    """Scan a specific path. Exit 1 on findings."""
    _scan(path, select, ignore, json_mode)


@app.command()
def rules(json_mode: JsonOpt = False) -> None:
    """List every lint rule."""
    from qontinuum.lint.rules import RULES

    rows = [{"code": code, "severity": sev, "title": title}
            for code, (sev, title, _) in sorted(RULES.items())]
    emit(rows, json_mode=json_mode, title="lint rules",
         columns=[("code", "Code"), ("severity", "Severity"), ("title", "Title")])


@app.command()
def explain(code: Annotated[str, typer.Argument(help="Rule code, e.g. Q001")]) -> None:
    """Explain one rule: what it catches and how to fix it."""
    from qontinuum.lint.rules import RULES

    rule = RULES.get(code.upper())
    if rule is None:
        fail(f"unknown rule {code!r}; run `qont lint rules`")
    severity, title, explanation = rule
    console.print(f"[bold]{code.upper()}[/bold] ({severity}) — {title}\n\n{explanation}")
