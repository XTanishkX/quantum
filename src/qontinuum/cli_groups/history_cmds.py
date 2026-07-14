"""qont history — interrogate the local run record (incl. git-bisect for quantum)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import EXIT_FAILURES, JsonOpt, console, emit, emit_object, fail

app = typer.Typer(help="Query and mine the local run history.", no_args_is_help=True)

PathOpt = Annotated[Path, typer.Option("--path", help="Project path holding .qontinuum/.")]


def _records(path: Path) -> list[dict]:
    from qontinuum.report.history import history_path, read_history

    records = read_history(path)
    if not records:
        fail(f"no history at {history_path(path)}; run `qont test` first")
    return records


def _summary_row(index: int, record: dict) -> dict:
    tally = record.get("tally", {})
    return {
        "run": index,
        "when": record["created_at"],
        "status": record["status"],
        "pass": tally.get("pass", 0),
        "fail": tally.get("fail", 0),
        "error": tally.get("error", 0),
        "shots": record.get("total_shots", 0),
        "seed": record.get("seed"),
        "commit": record.get("git_sha"),
    }


@app.command("list")
def list_cmd(
    path: PathOpt = Path("."),
    limit: Annotated[int, typer.Option(help="Most recent N runs.")] = 20,
    json_mode: JsonOpt = False,
) -> None:
    """Recent runs, newest last (run numbers are stable indices)."""
    records = _records(path)
    start = max(0, len(records) - limit)
    rows = [_summary_row(i, r) for i, r in enumerate(records)][start:]
    emit(rows, json_mode=json_mode, title=f"run history ({len(records)} total)",
         columns=[("run", "#"), ("when", "When"), ("status", "Status"), ("pass", "✓"),
                  ("fail", "✗"), ("error", "!"), ("shots", "Shots"), ("seed", "Seed"),
                  ("commit", "Commit")],
         right_align={"pass", "fail", "error", "shots"})


@app.command()
def show(
    run: Annotated[int, typer.Argument(help="Run index from `history list` (negatives ok).")],
    path: PathOpt = Path("."),
    json_mode: JsonOpt = False,
) -> None:
    """Full detail of one run: every test and check with statistics."""
    records = _records(path)
    try:
        record = records[run]
    except IndexError:
        fail(f"run {run} out of range (have {len(records)} runs)")
    if json_mode:
        print(json.dumps(record, indent=2))
        return
    emit_object(_summary_row(run if run >= 0 else len(records) + run, record),
                json_mode=False, title=f"run {run}")
    rows = []
    for test in record.get("tests", []):
        for check in test.get("checks", []) or [{}]:
            rows.append({
                "test": test["id"], "backend": test.get("backend"),
                "check": check.get("name", "—"), "status": check.get("status", test["status"]),
                "statistic": check.get("statistic"), "threshold": check.get("threshold"),
            })
    emit(rows, json_mode=False,
         columns=[("test", "Test"), ("backend", "Backend"), ("check", "Check"),
                  ("status", "Status"), ("statistic", "Statistic"), ("threshold", "Threshold")],
         right_align={"statistic", "threshold"})


@app.command("stats")
def stats_cmd(path: PathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Aggregate history: pass rate, flakiest test, provider usage, spend."""
    from qontinuum.intelligence import summarize_executions

    records = _records(path)
    fail_counts: dict[str, int] = {}
    for record in records:
        for test in record.get("tests", []):
            if test["status"] != "pass":
                fail_counts[test["id"]] = fail_counts.get(test["id"], 0) + 1
    flakiest = max(fail_counts.items(), key=lambda kv: kv[1], default=None)

    analytics = summarize_executions(records)
    emit_object(
        {
            # original keys preserved for backwards compatibility
            "runs": analytics["runs"],
            "pass_rate": analytics.get("suite_pass_rate"),
            "first_run": records[0]["created_at"],
            "last_run": records[-1]["created_at"],
            "total_shots": sum(r.get("total_shots", 0) for r in records),
            "most_failing_test": f"{flakiest[0]} ({flakiest[1]}x)" if flakiest else None,
            "cheapest_hw_estimates_sum": analytics.get("estimated_spend_usd"),
            # v0.4.0 execution analytics
            "hardware_runs": analytics.get("hardware_runs"),
            "hardware_success_rate": analytics.get("hardware_success_rate"),
            "providers_used": analytics.get("providers_used"),
        },
        json_mode=json_mode,
        title="history stats",
    )


@app.command()
def export(
    path: PathOpt = Path("."),
    fmt: Annotated[str, typer.Option("--format", help="csv | json")] = "csv",
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    """Export run summaries for spreadsheets or BI tools."""
    records = _records(path)
    rows = [_summary_row(i, r) for i, r in enumerate(records)]
    if fmt == "json":
        text = json.dumps(rows, indent=2)
    elif fmt == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        text = buffer.getvalue()
    else:
        fail(f"unknown format {fmt!r}; use csv or json")
    if out:
        out.write_text(text)
        console.print(f"[green]wrote[/green] {out} ({len(rows)} runs)")
    else:
        print(text, end="")


@app.command()
def prune(
    path: PathOpt = Path("."),
    keep: Annotated[int, typer.Option(help="Runs to keep (most recent).")] = 100,
) -> None:
    """Trim history to the most recent N runs."""
    from qontinuum.report.history import history_path

    records = _records(path)
    if len(records) <= keep:
        console.print(f"[dim]nothing to prune ({len(records)} <= {keep})[/dim]")
        return
    target = history_path(path)
    kept = records[-keep:]
    target.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in kept))
    console.print(f"[green]pruned[/green] {len(records) - keep} runs; kept {keep}")


@app.command()
def compare(
    run_a: Annotated[int, typer.Argument(help="Baseline run index.")],
    run_b: Annotated[int, typer.Argument(help="Comparison run index.")],
    path: PathOpt = Path("."),
    json_mode: JsonOpt = False,
) -> None:
    """Statistic-level regression between two recorded runs."""
    records = _records(path)
    try:
        a, b = records[run_a], records[run_b]
    except IndexError:
        fail(f"run index out of range (have {len(records)} runs)")

    def stats_of(record: dict) -> dict[tuple[str, str], float]:
        out = {}
        for test in record.get("tests", []):
            for check in test.get("checks", []):
                if check.get("statistic") is not None:
                    out[(test["id"], check["name"])] = check["statistic"]
        return out

    sa, sb = stats_of(a), stats_of(b)
    rows, regressions = [], 0
    for key in sorted(set(sa) | set(sb)):
        va, vb = sa.get(key), sb.get(key)
        delta = (vb - va) if (va is not None and vb is not None) else None
        rows.append({"test": key[0], "check": key[1], f"run_{run_a}": va,
                     f"run_{run_b}": vb, "delta": round(delta, 5) if delta is not None else None})
        if delta is not None and delta > 0:
            regressions += 1
    emit(rows, json_mode=json_mode, title=f"run {run_a} vs run {run_b} (positive Δ = worse)",
         columns=[("test", "Test"), ("check", "Check"), (f"run_{run_a}", f"Run {run_a}"),
                  (f"run_{run_b}", f"Run {run_b}"), ("delta", "Δ")],
         right_align={f"run_{run_a}", f"run_{run_b}", "delta"})
    if not json_mode:
        console.print(f"[dim]{regressions} statistic(s) moved in the wrong direction[/dim]")


@app.command()
def bisect(
    test_id: Annotated[str, typer.Argument(help="Test id, e.g. q_test_bell.py::bell_pair")],
    check: Annotated[str | None, typer.Option(help="Check name (default: first failing).")] = None,
    path: PathOpt = Path("."),
    json_mode: JsonOpt = False,
) -> None:
    """git-bisect for quantum: find the run where a check first went bad.

    Walks recorded history and reports the last good run, the first bad run,
    and the commit shas either side — so you know exactly which change (or
    which day's calibration) broke the physics.
    """
    records = _records(path)

    def status_in(record: dict) -> str | None:
        for test in record.get("tests", []):
            if test["id"] != test_id:
                continue
            checks = test.get("checks", [])
            if check:
                match = next((c for c in checks if c["name"] == check), None)
                return match["status"] if match else None
            if test["status"] != "pass":
                return "fail"
            return "pass"
        return None

    seen = [(i, status_in(r)) for i, r in enumerate(records)]
    seen = [(i, s) for i, s in seen if s is not None]
    if not seen:
        fail(f"test {test_id!r} never appears in history")
    first_bad = next((i for i, s in seen if s != "pass"), None)
    if first_bad is None:
        console.print(f"[green]{test_id} has never failed in recorded history[/green]")
        return
    last_good = max((i for i, s in seen if s == "pass" and i < first_bad), default=None)
    result = {
        "test": test_id,
        "last_good_run": last_good,
        "last_good_commit": records[last_good].get("git_sha") if last_good is not None else None,
        "last_good_at": records[last_good]["created_at"] if last_good is not None else None,
        "first_bad_run": first_bad,
        "first_bad_commit": records[first_bad].get("git_sha"),
        "first_bad_at": records[first_bad]["created_at"],
    }
    emit_object(result, json_mode=json_mode, title="bisect result")
    if not json_mode and result["last_good_commit"] and result["first_bad_commit"]:
        console.print(
            f"[dim]inspect code changes with:[/dim] git diff "
            f"{result['last_good_commit']} {result['first_bad_commit']}"
        )
    raise typer.Exit(EXIT_FAILURES)
