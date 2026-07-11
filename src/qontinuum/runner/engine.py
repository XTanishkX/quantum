"""Suite execution: discover tests, run circuits, evaluate checks and snapshots."""

from __future__ import annotations

from functools import partial
from pathlib import Path

import qontinuum
from qontinuum.assertions.asserts import (
    QuantumAssertionError,
    StatisticallyUnsoundError,
    assert_matches_baseline,
)
from qontinuum.report.schema import CheckResult, Status, SuiteResult, TestResult
from qontinuum.runner.backends import execute
from qontinuum.runner.discovery import DiscoveredTest, discover
from qontinuum.runner.snapshots import SnapshotStore


def run_suite(
    root: Path,
    *,
    seed: int | None = None,
    snapshot_alpha: float = 0.01,
    update_snapshots: bool = False,
) -> SuiteResult:
    """Run every discovered quantum test under ``root``."""
    store = SnapshotStore(root if root.is_dir() else root.parent)
    suite = SuiteResult(tool_version=qontinuum.__version__, seed=seed)
    for item in discover(root):
        suite.tests.append(
            _run_test(
                item,
                seed=seed,
                store=store,
                snapshot_alpha=snapshot_alpha,
                update_snapshots=update_snapshots,
            )
        )
    if update_snapshots:
        store.save()
    return suite


def _run_test(
    item: DiscoveredTest,
    *,
    seed: int | None,
    store: SnapshotStore,
    snapshot_alpha: float,
    update_snapshots: bool,
) -> TestResult:
    test = item.test
    result = TestResult(id=item.id, status=Status.PASS, backend=test.backend, shots=test.shots)
    try:
        circuit = test.build()
        run = execute(circuit, shots=test.shots, backend_spec=test.backend, seed=seed)
    except Exception as exc:
        result.status = Status.ERROR
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    result.circuit_hash = run.circuit_hash
    result.counts = run.counts
    result.duration_ms = round(run.duration_ms, 3)

    for check_fn in test.checks:
        result.checks.append(_evaluate(check_fn.__name__, partial(check_fn, run)))

    if test.snapshot:
        result.checks.append(
            _snapshot_check(
                item.id,
                run,
                store=store,
                alpha=snapshot_alpha,
                update=update_snapshots,
            )
        )

    statuses = {c.status for c in result.checks}
    if Status.ERROR in statuses:
        result.status = Status.ERROR
    elif Status.FAIL in statuses:
        result.status = Status.FAIL
    return result


def _evaluate(name: str, thunk) -> CheckResult:
    try:
        thunk()
        return CheckResult(name=name, status=Status.PASS)
    except QuantumAssertionError as exc:
        return CheckResult(
            name=name,
            status=Status.FAIL,
            message=str(exc),
            statistic=exc.statistic,
            threshold=exc.threshold,
        )
    except StatisticallyUnsoundError as exc:
        return CheckResult(name=name, status=Status.ERROR, message=str(exc))
    except AssertionError as exc:
        return CheckResult(name=name, status=Status.FAIL, message=str(exc) or "assertion failed")
    except Exception as exc:
        return CheckResult(name=name, status=Status.ERROR, message=f"{type(exc).__name__}: {exc}")


def _snapshot_check(
    test_id: str,
    run,
    *,
    store: SnapshotStore,
    alpha: float,
    update: bool,
) -> CheckResult:
    name = "snapshot"
    baseline = store.get(test_id)

    if update:
        store.put(
            test_id,
            circuit_hash=run.circuit_hash,
            backend=run.backend,
            shots=run.shots,
            counts=run.counts,
        )
        verb = "updated" if baseline else "created"
        return CheckResult(name=name, status=Status.PASS, message=f"snapshot {verb}")

    if baseline is None:
        return CheckResult(
            name=name,
            status=Status.ERROR,
            message="no snapshot recorded for this test; run `qont snapshot update`",
        )
    if baseline["circuit_hash"] != run.circuit_hash:
        return CheckResult(
            name=name,
            status=Status.FAIL,
            message=(
                "circuit changed since the snapshot was recorded; review the new "
                "distribution and run `qont snapshot update` to accept it"
            ),
        )
    return _evaluate(name, lambda: assert_matches_baseline(run, baseline["counts"], alpha=alpha))
