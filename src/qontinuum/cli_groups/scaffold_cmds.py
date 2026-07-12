"""qont init / doctor / completion, plus the env and schedule groups."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from qontinuum import config
from qontinuum.cli_util import (
    EXIT_FAILURES,
    JsonOpt,
    console,
    emit,
    emit_object,
    fail,
    project_root,
)

env_app = typer.Typer(help="Environment capture for reproducibility.", no_args_is_help=True)
schedule_app = typer.Typer(
    help="Generate scheduled GitHub workflows (files only, never pushed).",
    no_args_is_help=True,
)

_EXAMPLE_TEST = '''"""Example quantum test — run with `qont test`."""

from qiskit import QuantumCircuit

from qontinuum import assert_distribution, qtest


@qtest(shots=4000)
def bell_pair():
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


@bell_pair.check
def is_maximally_entangled(result):
    assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.05)
'''

_ACTION_WORKFLOW = """name: Quantum tests

on:
  pull_request:

permissions:
  contents: read
  pull-requests: write

jobs:
  quantum:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: XTanishkX/quantum/action@main
        with:
          path: .
          seed: "42"
"""

_PRE_COMMIT_HOOK = """#!/bin/sh
# Installed by `qont init --pre-commit`
qont lint || exit 1
"""

_GITIGNORE_BLOCK = """
# Qontinuum
.qontinuum/cache/
.qontinuum/history.jsonl
qontinuum-report.md
qontinuum-dashboard.html
"""


def register_flat(app: typer.Typer, *, panel: str) -> None:
    app.command(rich_help_panel=panel)(init)
    app.command(rich_help_panel=panel)(doctor)
    app.command(rich_help_panel=panel)(completion)


def init(
    path: Annotated[Path, typer.Argument(help="Directory to initialize.")] = Path("."),
    action: Annotated[bool, typer.Option("--action", help="Also write the PR workflow.")] = False,
    pre_commit: Annotated[
        bool, typer.Option("--pre-commit", help="Install a git pre-commit lint hook.")
    ] = False,
) -> None:
    """Scaffold a Qontinuum project: example test, config, gitignore entries."""
    path.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    example = path / "q_test_example.py"
    if not example.exists():
        example.write_text(_EXAMPLE_TEST)
        created.append(str(example))

    cfg = config.config_path(path)
    if not cfg.exists():
        config.set_value(path, "defaults.path", ".")
        created.append(str(cfg))

    gitignore = path / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else ""
    if ".qontinuum/cache/" not in existing:
        gitignore.write_text(existing + _GITIGNORE_BLOCK)
        created.append(str(gitignore) + " (appended)")

    if action:
        workflow = path / ".github" / "workflows" / "quantum.yml"
        if not workflow.exists():
            workflow.parent.mkdir(parents=True, exist_ok=True)
            workflow.write_text(_ACTION_WORKFLOW)
            created.append(str(workflow))

    if pre_commit:
        hooks = path / ".git" / "hooks"
        if hooks.is_dir():
            hook = hooks / "pre-commit"
            hook.write_text(_PRE_COMMIT_HOOK)
            hook.chmod(0o755)
            created.append(str(hook))
        else:
            console.print("[yellow]--pre-commit skipped: not a git repository[/yellow]")

    for item in created:
        console.print(f"[green]created[/green] {item}")
    if not created:
        console.print("[dim]nothing to do — already initialized[/dim]")
    console.print("\nNext: [bold]qont test[/bold] to run the example, "
                  "[bold]qont lint[/bold] to check it.")


def doctor(json_mode: JsonOpt = False) -> None:
    """Diagnose the environment: imports, extras, config, catalog freshness."""
    checks: list[dict] = []

    def check(name: str, ok: bool | None, detail: str) -> None:
        checks.append({"check": name, "status": {True: "ok", False: "FAIL", None: "info"}[ok],
                       "detail": detail})

    check("python", sys.version_info >= (3, 11), platform.python_version())
    for pkg, required in [("qiskit", True), ("qiskit-aer", True),
                          ("qiskit-qasm3-import", True), ("scipy", True),
                          ("qiskit-ibm-runtime", False), ("amazon-braket-sdk", False),
                          ("cirq-core", False), ("pennylane", False)]:
        try:
            version = importlib.metadata.version(pkg)
            check(pkg, True, version)
        except importlib.metadata.PackageNotFoundError:
            if required:
                check(pkg, False, "missing — reinstall qontinuum")
            else:
                check(pkg, None, "not installed (optional)")

    root = project_root()
    try:
        config.load(root)
        check("config", True, str(config.config_path(root)))
    except config.ConfigError as exc:
        check("config", False, str(exc))

    from qontinuum.cost import load_catalog

    catalog = load_catalog()
    verified = datetime.fromisoformat(catalog["verified"]).replace(tzinfo=UTC)
    age = (datetime.now(UTC) - verified).days
    check("pricing catalog", age <= 90, f"verified {catalog['verified']} ({age} days ago)")

    snap = root / ".qontinuum" / "snapshots.json"
    if snap.is_file():
        entries = len(json.loads(snap.read_text()).get("snapshots", {}))
        check("snapshots", True, f"{entries} recorded")

    failed = [c for c in checks if c["status"] == "FAIL"]
    emit(checks, json_mode=json_mode, title="qont doctor",
         columns=[("check", "Check"), ("status", "Status"), ("detail", "Detail")])
    if failed:
        raise typer.Exit(EXIT_FAILURES)


def completion(
    shell: Annotated[str, typer.Argument(help="bash | zsh | fish")] = "zsh",
) -> None:
    """Show how to enable shell completion."""
    if shell not in {"bash", "zsh", "fish"}:
        fail(f"unsupported shell {shell!r}; use bash, zsh, or fish")
    console.print(
        f"Run [bold]qont --install-completion {shell}[/bold] once, then restart the shell.\n"
        f"To inspect the script instead: [bold]qont --show-completion {shell}[/bold]"
    )


@env_app.command("show")
def env_show(json_mode: JsonOpt = False) -> None:
    """Print the execution environment relevant to reproducibility."""
    emit_object(_environment(), json_mode=json_mode, title="environment")


@env_app.command("lock")
def env_lock(
    out: Annotated[Path | None, typer.Option("--out", help="Lock file path.")] = None,
) -> None:
    """Write .qontinuum/env.lock.json capturing the current environment."""
    root = project_root()
    target = out or root / ".qontinuum" / "env.lock.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_environment(), indent=2) + "\n")
    console.print(f"[green]wrote[/green] {target}")


@env_app.command("diff")
def env_diff(json_mode: JsonOpt = False) -> None:
    """Compare the current environment against the lock file."""
    root = project_root()
    lock_file = root / ".qontinuum" / "env.lock.json"
    if not lock_file.is_file():
        fail(f"no lock file at {lock_file}; run `qont env lock` first")
    locked = json.loads(lock_file.read_text())
    current = _environment()
    rows = []
    for key in sorted(set(locked) | set(current)):
        a, b = locked.get(key), current.get(key)
        if a != b:
            rows.append({"component": key, "locked": a, "current": b})
    emit(rows, json_mode=json_mode, title="environment drift vs lock",
         columns=[("component", "Component"), ("locked", "Locked"), ("current", "Current")])
    if rows:
        raise typer.Exit(EXIT_FAILURES)
    if not json_mode:
        console.print("[green]environment matches the lock file[/green]")


def _environment() -> dict:
    env = {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    import contextlib

    for pkg in ["qontinuum", "qiskit", "qiskit-aer", "scipy", "numpy",
                "qiskit-ibm-runtime", "cirq-core", "pennylane"]:
        with contextlib.suppress(importlib.metadata.PackageNotFoundError):
            env[pkg] = importlib.metadata.version(pkg)
    return env


_SCHEDULE_TEMPLATE = """name: Qontinuum {cadence} regression

on:
  schedule:
    - cron: "{cron}"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  quantum-regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install "qontinuum[ibm]"
      - run: qont ci {path} --seed 42 --md regression-report.md
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: qontinuum-{cadence}-report
          path: regression-report.md
"""


def _write_schedule(cadence: str, cron: str, path: str, out: Path | None) -> None:
    target = out or Path(f".github/workflows/qontinuum-{cadence}.yml")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_SCHEDULE_TEMPLATE.format(cadence=cadence, cron=cron, path=path))
    console.print(f"[green]wrote[/green] {target} [dim](commit and push to enable)[/dim]")


@schedule_app.command()
def nightly(
    path: Annotated[str, typer.Option(help="Test path for the scheduled run.")] = ".",
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    """Emit a nightly (03:00 UTC) regression workflow."""
    _write_schedule("nightly", "0 3 * * *", path, out)


@schedule_app.command()
def weekly(
    path: Annotated[str, typer.Option(help="Test path for the scheduled run.")] = ".",
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    """Emit a weekly (Monday 03:00 UTC) regression workflow."""
    _write_schedule("weekly", "0 3 * * 1", path, out)
