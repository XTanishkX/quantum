"""qont providers — provenance and freshness of the pricing catalog."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import typer

from qontinuum.cli_util import EXIT_FAILURES, JsonOpt, console, emit

app = typer.Typer(help="Pricing-catalog provenance.", no_args_is_help=True)


@app.command("list")
def list_cmd(json_mode: JsonOpt = False) -> None:
    """Providers, device counts, verification date, and sources."""
    from qontinuum.cost import load_catalog

    catalog = load_catalog()
    verified = catalog["verified"]
    age_days = (datetime.now(UTC) - datetime.fromisoformat(verified).replace(tzinfo=UTC)).days
    rows = [
        {
            "provider": provider["display"],
            "devices": len(provider["devices"]),
            "verified": verified,
            "age_days": age_days,
        }
        for provider in catalog["providers"].values()
    ]
    emit(rows, json_mode=json_mode, title="pricing catalog provenance",
         columns=[("provider", "Provider"), ("devices", "Devices"),
                  ("verified", "Prices verified"), ("age_days", "Age (days)")],
         right_align={"devices", "age_days"})
    if not json_mode:
        for source in catalog["sources"]:
            console.print(f"  [dim]source:[/dim] {source}")
        if age_days > 90:
            console.print(f"[yellow]catalog is {age_days} days old — re-verify prices[/yellow]")


@app.command()
def verify(
    timeout: Annotated[float, typer.Option(help="Per-request timeout (seconds).")] = 10.0,
    json_mode: JsonOpt = False,
) -> None:
    """Check that every catalog source URL is still reachable (network)."""
    import urllib.error
    import urllib.request

    from qontinuum.cost import load_catalog

    rows, failures = [], 0
    for url in load_catalog()["sources"]:
        try:
            request = urllib.request.Request(url, method="HEAD",
                                             headers={"User-Agent": "qontinuum-cli"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                rows.append({"source": url, "status": response.status, "ok": True})
        except urllib.error.HTTPError as exc:
            ok = exc.code < 500 and exc.code != 404
            failures += 0 if ok else 1
            rows.append({"source": url, "status": exc.code, "ok": ok})
        except Exception as exc:
            failures += 1
            rows.append({"source": url, "status": str(exc), "ok": False})
    emit(rows, json_mode=json_mode, title="catalog source reachability",
         columns=[("source", "Source"), ("status", "Status"), ("ok", "OK")])
    if not json_mode:
        console.print("[dim]prices themselves must be re-verified by a human — "
                      "update catalog.yaml's `verified` date when you do[/dim]")
    if failures:
        raise typer.Exit(EXIT_FAILURES)
