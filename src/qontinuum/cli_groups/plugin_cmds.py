"""qont plugin — inspect and diagnose the provider / backend / SDK plugins."""

from __future__ import annotations

from importlib.util import find_spec
from typing import Annotated

import typer

from qontinuum.cli_util import EXIT_FAILURES, JsonOpt, console, emit, emit_object, fail

app = typer.Typer(
    help="Discover and diagnose provider, backend, and SDK plugins.",
    no_args_is_help=True,
)

KindOpt = Annotated[
    str | None,
    typer.Option("--kind", help="Filter by kind: provider, backend, or sdk."),
]


@app.command("list")
def list_cmd(kind: KindOpt = None, json_mode: JsonOpt = False) -> None:
    """Every discovered plugin, built-in and installed."""
    from qontinuum.plugins import get_registry

    records = get_registry().records()
    if kind:
        records = [r for r in records if r.kind == kind]
    rows = [
        {
            "name": r.name,
            "kind": r.kind,
            "source": r.source,
            "available": r.available,
            "requires": ", ".join(r.requires) or "—",
            "note": r.error or (f"shadows {r.shadows}" if r.shadows else r.summary),
        }
        for r in records
    ]
    emit(
        rows,
        json_mode=json_mode,
        title="qontinuum plugins",
        columns=[
            ("name", "Name"),
            ("kind", "Kind"),
            ("source", "Source"),
            ("available", "Loaded"),
            ("requires", "Requires"),
            ("note", "Notes"),
        ],
    )


@app.command()
def show(
    name: Annotated[str, typer.Argument(help="Plugin name, e.g. ibm.")],
    kind: KindOpt = None,
    json_mode: JsonOpt = False,
) -> None:
    """Full detail for one plugin (disambiguate same-named ones with --kind)."""
    from qontinuum.plugins import get_registry

    matches = [
        r
        for r in get_registry().records()
        if r.name == name and (kind is None or r.kind == kind)
    ]
    if not matches:
        fail(f"no plugin named {name!r}; run `qont plugin list`")
    if len(matches) > 1:
        kinds = ", ".join(sorted(r.kind for r in matches))
        fail(f"{name!r} is ambiguous across kinds ({kinds}); pass --kind")
    record = matches[0]
    missing = _missing_requirements(record)
    detail = {
        "name": record.name,
        "kind": record.kind,
        "source": record.source,
        "loaded": record.available,
        "summary": record.summary or None,
        "requires": ", ".join(record.requires) or None,
        "missing_deps": ", ".join(missing) or None,
        "install_hint": record.install_hint() if missing else None,
        "distribution": record.dist,
        "shadows": record.shadows,
        "error": record.error,
        "implementation": _impl_path(record),
    }
    emit_object(detail, json_mode=json_mode, title=f"plugin {record.name} ({record.kind})")


@app.command()
def doctor(json_mode: JsonOpt = False) -> None:
    """Diagnose plugin health: what loaded, what needs an extra, what's broken.

    Exit is non-zero only when a *built-in* plugin fails to load (real
    breakage). Third-party plugins that merely need an optional dependency are
    reported but do not fail the check — they are opt-in by design.
    """
    from qontinuum.plugins import get_registry

    rows: list[dict] = []
    broken_builtins = 0
    for record in get_registry().records():
        missing = _missing_requirements(record)
        if not record.available:
            status = "broken"
            if record.source == "builtin":
                broken_builtins += 1
        elif missing:
            status = "needs-deps"
        else:
            status = "ok"
        rows.append(
            {
                "name": record.name,
                "kind": record.kind,
                "source": record.source,
                "status": status,
                "detail": record.error
                or (record.install_hint() if missing else "ready"),
            }
        )
    emit(
        rows,
        json_mode=json_mode,
        title="plugin doctor",
        columns=[
            ("name", "Name"),
            ("kind", "Kind"),
            ("source", "Source"),
            ("status", "Status"),
            ("detail", "Detail"),
        ],
    )
    if not json_mode:
        ready = sum(1 for r in rows if r["status"] == "ok")
        console.print(f"[dim]{ready}/{len(rows)} plugins ready.[/dim]")
    if broken_builtins:
        raise typer.Exit(EXIT_FAILURES)


def _missing_requirements(record) -> list[str]:
    """Required modules that are not importable in this environment."""
    if not record.available:
        return []
    missing = []
    for module in record.requires:
        try:
            if find_spec(module) is None:
                missing.append(module)
        except (ImportError, ValueError):
            missing.append(module)
    return missing


def _impl_path(record) -> str | None:
    plugin = record.plugin
    if plugin is None:
        return None
    cls = type(plugin)
    return f"{cls.__module__}.{cls.__qualname__}"
