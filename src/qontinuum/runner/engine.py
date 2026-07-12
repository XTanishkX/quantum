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
from qontinuum.assertions.context import capture_assertions
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
    use_cache: bool = False,
) -> SuiteResult:
    """Run every discovered quantum test under ``root``.

    With ``use_cache`` and a seed, unchanged circuits reuse counts from the
    content-addressed result cache instead of re-simulating.
    """
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
                cache_root=root if (use_cache and seed is not None) else None,
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
    cache_root: Path | None = None,
) -> TestResult:
    test = item.test
    result = TestResult(id=item.id, status=Status.PASS, backend=test.backend, shots=test.shots)
    try:
        circuit = test.build()
        run = _execute_maybe_cached(item, circuit, seed=seed, cache_root=cache_root)
    except Exception as exc:
        result.status = Status.ERROR
        result.error = f"{type(exc).__name__}: {exc}"
        return result
    result.cached = bool(run.metadata.get("cached"))

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


def _execute_maybe_cached(item: DiscoveredTest, circuit, *, seed, cache_root):
    """Execute, or serve counts from the result cache for seeded runs."""
    if cache_root is None:
        return execute(circuit, shots=item.test.shots, backend_spec=item.test.backend, seed=seed)

    from qontinuum import cache
    from qontinuum.circuits import circuit_hash
    from qontinuum.runner.result import RunResult

    digest = circuit_hash(circuit)
    key = cache.cache_key(digest, item.test.backend, item.test.shots, seed)
    counts = cache.get(cache_root, key)
    if counts is not None:
        return RunResult(
            counts=counts, shots=item.test.shots, backend=item.test.backend,
            circuit_hash=digest, seed=seed, duration_ms=0.0, metadata={"cached": True},
        )
    run = execute(circuit, shots=item.test.shots, backend_spec=item.test.backend, seed=seed)
    cache.put(cache_root, key, run.counts, meta={"test": item.id})
    return run


def _evaluate(name: str, thunk) -> CheckResult:
    with capture_assertions() as events:
        try:
            thunk()
            result = CheckResult(name=name, status=Status.PASS)
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
            return CheckResult(
                name=name, status=Status.FAIL, message=str(exc) or "assertion failed"
            )
        except Exception as exc:
            return CheckResult(
                name=name, status=Status.ERROR, message=f"{type(exc).__name__}: {exc}"
            )
    # Passing checks keep their computed statistic (last assertion in the
    # check) so trend charts work on healthy suites, not just broken ones.
    if events:
        result.statistic = events[-1].statistic
        result.threshold = events[-1].threshold
    return result


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
