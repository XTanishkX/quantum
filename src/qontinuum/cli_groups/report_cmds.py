"""qont report — turn suite results into every format a pipeline wants."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from qontinuum.cli_util import console, fail, project_root

app = typer.Typer(
    help="Render suite results (from --from suite.json, or by running the suite).",
    no_args_is_help=True,
)

FromOpt = Annotated[
    Path | None,
    typer.Option("--from", help="Suite-result JSON (qont test --json). Default: run now."),
]
PathOpt = Annotated[Path, typer.Option("--path", help="Test path when running fresh.")]
SeedOpt = Annotated[int | None, typer.Option()]
OutOpt = Annotated[Path | None, typer.Option("--out", help="Write to file instead of stdout.")]


def _suite(source: Path | None, path: Path, seed: int | None):
    from qontinuum.report.schema import SuiteResult
    from qontinuum.runner.engine import run_suite

    if source is not None:
        if not source.is_file():
            fail(f"no such file: {source}")
        try:
            return SuiteResult.model_validate_json(source.read_text())
        except Exception as exc:
            fail(f"{source} is not a suite-result JSON: {exc}")
    return run_suite(path, seed=seed)


def _write(text: str, out: Path | None) -> None:
    if out:
        out.write_text(text)
        console.print(f"[green]wrote[/green] {out}")
    else:
        print(text, end="" if text.endswith("\n") else "\n")


@app.command()
def junit(
    source: FromOpt = None, path: PathOpt = Path("."), seed: SeedOpt = None, out: OutOpt = None
) -> None:
    """JUnit XML — Jenkins/GitLab/Buildkite render quantum checks natively."""
    from qontinuum import config
    from qontinuum.report.exporters import render_junit

    suite = _suite(source, path, seed)
    name = config.effective(project_root(path))["report.junit_suite_name"]
    _write(render_junit(suite, suite_name=name), out)


@app.command()
def badge(
    source: FromOpt = None, path: PathOpt = Path("."), seed: SeedOpt = None, out: OutOpt = None,
    label: Annotated[str, typer.Option()] = "quantum tests",
) -> None:
    """SVG status badge from the suite result."""
    from qontinuum.report.exporters import render_badge

    suite = _suite(source, path, seed)
    _write(render_badge(suite.status.value, label=label), out)


@app.command()
def md(
    source: FromOpt = None, path: PathOpt = Path("."), seed: SeedOpt = None, out: OutOpt = None
) -> None:
    """Markdown report (same renderer as the PR comment, without cost table)."""
    from qontinuum.report.markdown import render_report

    _write(render_report(_suite(source, path, seed), []), out)


@app.command()
def pr(
    source: FromOpt = None, path: PathOpt = Path("."), seed: SeedOpt = None, out: OutOpt = None
) -> None:
    """The full sticky PR comment (results + hardware cost table), rendered locally."""
    from qontinuum.cost import estimate_suite
    from qontinuum.report.markdown import render_report
    from qontinuum.runner.discovery import discover

    suite = _suite(source, path, seed)
    pairs = []
    for item in discover(path):
        try:
            pairs.append((item.test.build(), item.test.shots))
        except Exception:
            continue
    _write(render_report(suite, estimate_suite(pairs) if pairs else []), out)


@app.command("json")
def json_cmd(
    source: FromOpt = None, path: PathOpt = Path("."), seed: SeedOpt = None, out: OutOpt = None
) -> None:
    """The raw versioned suite-result JSON."""
    suite = _suite(source, path, seed)
    _write(suite.model_dump_json(indent=2), out)


@app.command()
def html(
    path: PathOpt = Path("."), out: OutOpt = None
) -> None:
    """Self-contained HTML dashboard from run history (alias of qont dashboard)."""
    from qontinuum.report.dashboard import render_dashboard
    from qontinuum.report.history import read_history

    records = read_history(path)
    if not records:
        fail("no history recorded; run `qont test` first")
    _write(render_dashboard(records), out or Path("qontinuum-dashboard.html"))


@app.command()
def summary(
    source: FromOpt = None, path: PathOpt = Path("."), seed: SeedOpt = None,
) -> None:
    """One-line machine-greppable summary (for shell pipelines)."""
    suite = _suite(source, path, seed)
    tally = suite.tally()
    print(f"status={suite.status.value} pass={tally['pass']} fail={tally['fail']} "
          f"error={tally['error']} tests={len(suite.tests)} "
          f"shots={sum(t.shots for t in suite.tests)}")
