"""Lint engine: discover tests, probe each once, run every rule."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from qontinuum.lint.rules import RULES, Finding, LintContext, run_rules

#: Probe simulations are capped so linting stays fast even for 1M-shot tests;
#: rules that reason about the *configured* shots use ctx.test.shots, not this.
_PROBE_SHOTS_CAP = 1000


def lint_path(
    root: Path,
    *,
    select: set[str] | None = None,
    ignore: set[str] | None = None,
) -> list[Finding]:
    from qontinuum.runner.backends import execute
    from qontinuum.runner.discovery import discover
    from qontinuum.runner.snapshots import SnapshotStore

    store = SnapshotStore(root if root.is_dir() else root.parent)
    findings: list[Finding] = []
    for item in discover(root):
        ctx = LintContext(
            test_id=item.id,
            test=item.test,
            circuit=None,
            build_error=None,
            has_snapshot_baseline=store.get(item.id) is not None,
        )
        try:
            ctx.circuit = item.test.build()
        except Exception as exc:
            ctx.build_error = str(exc)
        if ctx.circuit is not None and item.test.checks:
            ctx.events = _probe_events(item, ctx.circuit, execute)
        findings.extend(run_rules(ctx))

    if select:
        findings = [f for f in findings if f.code in select]
    if ignore:
        findings = [f for f in findings if f.code not in ignore]
    unknown = (select or set()) - set(RULES) | (ignore or set()) - set(RULES)
    if unknown:
        raise ValueError(f"unknown rule code(s): {', '.join(sorted(unknown))}")
    return findings


def _probe_events(item, circuit, execute):
    """One cheap ideal run to capture thresholds the checks actually use."""
    from qontinuum.assertions.context import capture_assertions

    shots = min(item.test.shots, _PROBE_SHOTS_CAP)
    try:
        run = execute(circuit, shots=shots, backend_spec="aer", seed=11)
    except Exception:
        return []
    import contextlib

    events = []
    for check_fn in item.test.checks:
        with capture_assertions() as captured, contextlib.suppress(Exception):
            # failures are fine; we only want the recorded thresholds
            partial(check_fn, run)()
        events.extend(captured)
    return events
