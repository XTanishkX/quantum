"""qont telemetry — opt in/out of the Quantum Intelligence Network, and stay in control.

Everything here is transparent by design: `enable` states exactly what is shared,
`preview` shows the literal records that would be sent, and nothing leaves the
machine without an explicit `sync`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import JsonOpt, console, emit, emit_object

app = typer.Typer(
    help="Opt-in, anonymous community intelligence (off by default).",
    no_args_is_help=True,
)

PathOpt = Annotated[Path, typer.Option("--path", help="Project path holding .qontinuum/.")]

#: Plain-English description of the only data ever shared.
_SHARED_FIELDS = [
    "provider & device (public catalog ids)",
    "outcome (pass/fail), runtime, queue time, estimated cost",
    "shots bucket, calibration age, routing strategy",
    "tool version, calendar day, and a random anonymous install id",
]
_NEVER_SHARED = [
    "circuits, gates, or QASM",
    "measurement counts or probability distributions",
    "snapshots, test ids, file paths, git shas, or seeds",
    "credentials, API keys, or any personal information",
]


@app.command()
def status(path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Show consent, endpoint, queued records, and community cache state."""
    from qontinuum.telemetry import consent, load_community, outbox

    enabled = consent.is_enabled(path)
    aggregate = load_community(path)
    install = consent.install_id(path)
    info = {
        "enabled": enabled,
        "endpoint": consent.endpoint(path) or "(none — local only)",
        "install_id": (install[:8] + "…") if install else "(not set)",
        "queued_records": outbox.count(path),
        "community_devices": len(aggregate.devices) if aggregate else 0,
        "community_generated_at": aggregate.generated_at if aggregate else None,
    }
    emit_object(info, json_mode=json_mode, title="telemetry status")
    if not json_mode and not enabled:
        console.print("[dim]Telemetry is off. Enable with `qont telemetry enable`.[/dim]")


@app.command()
def enable(path: PathOpt = Path(".")) -> None:
    """Opt in to contributing anonymous execution metadata."""
    from qontinuum.telemetry import consent

    console.print("[bold]Qontinuum will share only this anonymous metadata:[/bold]")
    for item in _SHARED_FIELDS:
        console.print(f"  [green]•[/green] {item}")
    console.print("[bold]It will never share:[/bold]")
    for item in _NEVER_SHARED:
        console.print(f"  [red]✗[/red] {item}")
    install = consent.enable(path)
    console.print(
        f"\n[green]Telemetry enabled.[/green] Anonymous install id: [dim]{install}[/dim]\n"
        "Records queue locally and only leave on `qont telemetry sync`. "
        "Opt out anytime with `qont telemetry disable`."
    )


@app.command()
def disable(path: PathOpt = Path(".")) -> None:
    """Opt out. Nothing further is captured or sent."""
    from qontinuum.telemetry import consent

    consent.disable(path)
    console.print("[green]Telemetry disabled.[/green] Queued records are kept until you "
                  "`qont telemetry sync` or `clear` them.")


@app.command()
def preview(path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Show exactly what would be contributed from your run history."""
    from qontinuum.report.history import read_history
    from qontinuum.telemetry import preview as build_preview

    records = build_preview(path, read_history(path))
    rows = [
        {
            "day": r.ts_day,
            "provider": r.provider,
            "device": r.device,
            "outcome": r.outcome,
            "runtime_s": r.runtime_s,
            "cost_usd": r.estimated_cost_usd,
            "shots": r.shots_bucket,
        }
        for r in records
    ]
    emit(rows, json_mode=json_mode, title=f"telemetry preview — {len(rows)} record(s)",
         columns=[("day", "Day"), ("provider", "Provider"), ("device", "Device"),
                  ("outcome", "Outcome"), ("runtime_s", "Runtime"), ("cost_usd", "Est. cost"),
                  ("shots", "Shots")],
         right_align={"runtime_s", "cost_usd"})
    if not json_mode:
        console.print("[dim]This is the complete payload — no circuits, counts, or identity.[/dim]")


@app.command()
def sync(
    path: PathOpt = Path("."),
    timeout: Annotated[float, typer.Option(help="Per-request timeout (seconds).")] = 10.0,
    json_mode: JsonOpt = False,
) -> None:
    """Flush queued records to the network (safe offline; never blocks a run)."""
    from qontinuum.telemetry import sync as run_sync

    result = run_sync(path, timeout=timeout)
    emit_object(
        {
            "ok": result.ok,
            "sent": result.sent,
            "queued": result.queued,
            "endpoint": result.endpoint or "(none)",
            "community_updated": result.community_updated,
            "detail": result.detail,
        },
        json_mode=json_mode,
        title="telemetry sync",
    )


@app.command()
def community(path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Show the locally cached community-intelligence snapshot."""
    from qontinuum.telemetry import load_community

    aggregate = load_community(path)
    if aggregate is None:
        from qontinuum.cli_util import fail

        fail("no community snapshot cached; run `qont telemetry sync` with an endpoint set")
    rows = [
        {"device": device, "samples": stat.samples, "success_rate": stat.success_rate,
         "avg_runtime_s": stat.avg_runtime_s, "avg_cost_usd": stat.avg_cost_usd}
        for device, stat in sorted(aggregate.devices.items())
    ]
    emit(rows, json_mode=json_mode,
         title=f"community intelligence — generated {aggregate.generated_at}",
         columns=[("device", "Device"), ("samples", "Samples"), ("success_rate", "Success"),
                  ("avg_runtime_s", "Avg runtime"), ("avg_cost_usd", "Avg cost")],
         right_align={"samples", "success_rate", "avg_runtime_s", "avg_cost_usd"})


@app.command()
def clear(path: PathOpt = Path(".")) -> None:
    """Delete all locally queued records without sending them."""
    from qontinuum.telemetry import outbox

    dropped = outbox.clear(path)
    console.print(f"[green]cleared[/green] {dropped} queued record(s)")
