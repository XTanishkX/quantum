"""Command groups mounted onto the main typer app (one module per noun)."""

from __future__ import annotations

import typer

PANEL_PROJECT = "Project & environment"
PANEL_CIRCUITS = "Circuits"
PANEL_ANALYSIS = "Analysis & quality"
PANEL_STATE = "State, history & spend"
PANEL_HARDWARE = "Hardware & providers"
PANEL_REPORTS = "Reports"
PANEL_CORE = "Core workflow"


def register(app: typer.Typer) -> None:
    from qontinuum.cli_groups import (
        bench_cmds,
        budget_cmds,
        cache_cmds,
        circuit_cmds,
        config_cmds,
        device_cmds,
        history_cmds,
        lint_cmds,
        misc_cmds,
        noise_cmds,
        pack_cmds,
        providers_cmds,
        registry_cmds,
        report_cmds,
        scaffold_cmds,
        shots_cmds,
        stats_cmds,
    )

    app.add_typer(config_cmds.app, name="config", rich_help_panel=PANEL_PROJECT)
    app.add_typer(scaffold_cmds.env_app, name="env", rich_help_panel=PANEL_PROJECT)
    app.add_typer(scaffold_cmds.schedule_app, name="schedule", rich_help_panel=PANEL_PROJECT)
    scaffold_cmds.register_flat(app, panel=PANEL_PROJECT)

    app.add_typer(circuit_cmds.app, name="circuit", rich_help_panel=PANEL_CIRCUITS)
    app.add_typer(device_cmds.app, name="device", rich_help_panel=PANEL_HARDWARE)
    app.add_typer(providers_cmds.app, name="providers", rich_help_panel=PANEL_HARDWARE)
    app.add_typer(history_cmds.app, name="history", rich_help_panel=PANEL_STATE)
    app.add_typer(budget_cmds.app, name="budget", rich_help_panel=PANEL_STATE)
    app.add_typer(cache_cmds.app, name="cache", rich_help_panel=PANEL_STATE)
    app.add_typer(registry_cmds.app, name="registry", rich_help_panel=PANEL_STATE)
    app.add_typer(pack_cmds.app, name="pack", rich_help_panel=PANEL_STATE)
    app.add_typer(stats_cmds.app, name="stats", rich_help_panel=PANEL_ANALYSIS)
    app.add_typer(shots_cmds.app, name="shots", rich_help_panel=PANEL_ANALYSIS)
    app.add_typer(noise_cmds.app, name="noise", rich_help_panel=PANEL_ANALYSIS)
    app.add_typer(bench_cmds.app, name="bench", rich_help_panel=PANEL_ANALYSIS)
    app.add_typer(lint_cmds.app, name="lint", rich_help_panel=PANEL_ANALYSIS)
    app.add_typer(report_cmds.app, name="report", rich_help_panel=PANEL_REPORTS)
    misc_cmds.register_flat(app)
