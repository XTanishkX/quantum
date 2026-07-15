"""qont recommend / plan / health — the execution-intelligence commands.

Thin renderers over :mod:`qontinuum.intelligence`: they gather the workload,
call the pure engine, and print. All reasoning lives in the engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_groups import PANEL_INTEL
from qontinuum.cli_util import JsonOpt, console, emit, emit_object, fail
from qontinuum.intelligence import Strategy

PathArg = Annotated[Path, typer.Argument(help="Test file or directory to plan for.")]
StrategyOpt = Annotated[
    Strategy,
    typer.Option("--strategy", "-s", help="What to optimize for."),
]
BudgetOpt = Annotated[
    float | None, typer.Option("--budget", help="Only consider devices at/under this USD.")
]


def register_flat(app: typer.Typer) -> None:
    app.command(rich_help_panel=PANEL_INTEL)(recommend)
    app.command(rich_help_panel=PANEL_INTEL)(plan)
    app.command(rich_help_panel=PANEL_INTEL)(health)


def _gather_workload(path: Path):
    """Discover tests and build (profiles, shots, estimates, catalog)."""
    from qontinuum.cost import estimate_suite, load_catalog, profile_circuit
    from qontinuum.runner.discovery import discover

    if not path.exists():
        fail(f"path not found: {path}")
    items = discover(path)
    if not items:
        fail("no quantum tests found (looked for q_test_*.py)")
    circuits = [item.test.build() for item in items]
    profiles = [profile_circuit(qc) for qc in circuits]
    shots = [item.test.shots for item in items]
    pairs = list(zip(circuits, shots, strict=True))
    return profiles, shots, estimate_suite(pairs), load_catalog()


def _health(path: Path, catalog: dict):
    from qontinuum.intelligence import assess_health
    from qontinuum.report.history import read_history
    from qontinuum.telemetry import load_community

    # Community intelligence is used only if a snapshot has been synced locally;
    # otherwise this is exactly the offline catalog + history assessment.
    return assess_health(catalog, read_history(path), community=load_community(path))


def _print_explanation(explanation) -> None:
    console.print(f"\n[bold]Why:[/bold] {explanation.summary}")
    for reason in explanation.reasons:
        console.print(f"  [green]•[/green] {reason}")
    for assumption in explanation.assumptions:
        console.print(f"  [dim]assumes:[/dim] {assumption}")
    for missing in explanation.missing:
        console.print(f"  [yellow]missing:[/yellow] {missing}")
    console.print(f"  [dim]confidence: {explanation.confidence:.0%}[/dim]")


def recommend(
    path: PathArg = Path("."),
    strategy: StrategyOpt = Strategy.BALANCED,
    budget: BudgetOpt = None,
    json_mode: JsonOpt = False,
) -> None:
    """Rank hardware for the discovered workload and explain the top choice."""
    from qontinuum.intelligence import recommend as run_recommend

    profiles, shots, estimates, catalog = _gather_workload(path)
    recs = run_recommend(
        profiles, shots, estimates, catalog,
        strategy=strategy, budget=budget, health=_health(path, catalog),
    )
    if json_mode:
        print(_json([r.model_dump() for r in recs]))
        return

    rows = [
        {
            "rank": i,
            "device": r.display,
            "provider": r.provider,
            "success": r.success_prob,
            "cost": r.usd,
            "runtime_s": r.runtime_s,
            "reliability": r.reliability,
            "risks": len(r.risks),
        }
        for i, r in enumerate(recs, 1)
        if r.feasible
    ]
    emit(rows, json_mode=False,
         title=f"execution recommendations — optimizing for {strategy.value}",
         columns=[("rank", "#"), ("device", "Device"), ("provider", "Provider"),
                  ("success", "Success"), ("cost", "Cost"), ("runtime_s", "Runtime"),
                  ("reliability", "Reliability"), ("risks", "Risks")],
         right_align={"rank", "success", "cost", "runtime_s", "reliability", "risks"})

    feasible = [r for r in recs if r.feasible]
    if feasible and feasible[0].explanation:
        _print_explanation(feasible[0].explanation)
        rejected = [r for r in feasible[1:4]]
        if rejected:
            console.print("\n[bold]Runners-up:[/bold]")
            for r in rejected:
                note = r.risks[0] if r.risks else "viable alternative"
                console.print(f"  [dim]{r.display}[/dim] — {note}")


def plan(
    path: PathArg = Path("."),
    strategy: StrategyOpt = Strategy.BALANCED,
    budget: BudgetOpt = None,
    json_mode: JsonOpt = False,
) -> None:
    """Produce a concrete execution plan: device, estimates, risks, fallbacks."""
    from qontinuum.intelligence import PlanningError, build_plan
    from qontinuum.intelligence import recommend as run_recommend

    profiles, shots, estimates, catalog = _gather_workload(path)
    recs = run_recommend(
        profiles, shots, estimates, catalog,
        strategy=strategy, budget=budget, health=_health(path, catalog),
    )
    try:
        execution_plan = build_plan(recs, strategy=strategy, workload=str(path), budget=budget)
    except PlanningError as exc:
        fail(str(exc))

    if json_mode:
        print(execution_plan.model_dump_json(indent=2))
        return

    emit_object(
        {
            "workload": execution_plan.workload,
            "strategy": execution_plan.strategy,
            "provider": execution_plan.provider,
            "device": execution_plan.display,
            "estimated_runtime_s": execution_plan.estimated_runtime_s,
            "estimated_queue_s": execution_plan.estimated_queue_s,
            "estimated_cost_usd": execution_plan.estimated_cost_usd,
            "expected_fidelity": execution_plan.expected_fidelity,
            "risk_level": execution_plan.risk_level,
            "confidence": execution_plan.confidence,
            "within_budget": execution_plan.within_budget,
        },
        json_mode=False,
        title="execution plan",
    )
    if execution_plan.risks:
        console.print("\n[bold]Risks:[/bold]")
        for risk in execution_plan.risks:
            console.print(f"  [yellow]•[/yellow] {risk}")
    if execution_plan.fallbacks:
        console.print("\n[bold]Fallbacks:[/bold]")
        for fb in execution_plan.fallbacks:
            console.print(f"  [dim]{fb.display}[/dim] — {fb.reason}")
    _print_explanation(execution_plan.explanation)


HealthPathOpt = Annotated[
    Path, typer.Option("--path", help="Project path holding .qontinuum/.")
]


def health(path: HealthPathOpt = Path("."), json_mode: JsonOpt = False) -> None:
    """Provider health: per-device reliability from calibration and local history."""
    from qontinuum.cost import load_catalog

    healths = _health(path, load_catalog())
    if json_mode:
        print(_json([h.model_dump() for h in healths]))
        return
    rows = [
        {
            "device": h.display,
            "provider": h.provider,
            "reliability": h.reliability,
            "calibration": h.calibration_quality,
            "empirical": h.empirical_success,
            "community": h.community_success,
            "runs": h.recent_runs,
            "sources": ", ".join(h.data_sources) or "—",
            "confidence": h.confidence,
        }
        for h in healths
    ]
    emit(rows, json_mode=False, title="provider health",
         columns=[("device", "Device"), ("provider", "Provider"),
                  ("reliability", "Reliability"), ("calibration", "Calib. quality"),
                  ("empirical", "Empirical"), ("community", "Community"), ("runs", "Runs"),
                  ("sources", "Evidence"), ("confidence", "Confidence")],
         right_align={"reliability", "calibration", "empirical", "community", "runs",
                      "confidence"})
    console.print("[dim]Reliability blends catalog calibration with local run history and "
                  "(if synced) community intelligence; confidence reflects the evidence behind "
                  "each row.[/dim]")


def _json(obj) -> str:
    import json

    return json.dumps(obj, indent=2, default=str)
