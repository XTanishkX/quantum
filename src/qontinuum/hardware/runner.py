"""Guarded execution of a test suite on real hardware.

Nothing is submitted until the whole suite's estimated cost clears the
``max_cost`` budget — the guard is all-or-nothing so a suite can't die
half-submitted with money already spent on the first tests.
"""

from __future__ import annotations

import time
from functools import partial
from pathlib import Path

import qontinuum
from qontinuum.circuits import circuit_hash
from qontinuum.cost.estimator import estimate_circuit, load_catalog
from qontinuum.hardware.base import HardwareAdapter, SpendGuardError
from qontinuum.report.schema import Status, SuiteResult, TestResult
from qontinuum.runner.discovery import discover
from qontinuum.runner.engine import _evaluate
from qontinuum.runner.result import RunResult


def estimate_hardware_cost(
    circuits_shots: list[tuple], catalog_device: tuple[str, str]
) -> float:
    """Suite cost on one specific device; raises SpendGuardError if unpriceable."""
    catalog = load_catalog()
    provider_key, device_key = catalog_device
    total = 0.0
    for circuit, shots in circuits_shots:
        estimates = estimate_circuit(circuit, shots, catalog=catalog)
        est = next(e for e in estimates if e.device == device_key)
        if not est.feasible:
            raise SpendGuardError(
                f"circuit does not fit {provider_key}:{device_key} — {est.note}"
            )
        if est.usd is None:
            raise SpendGuardError(
                f"{provider_key}:{device_key} has no public dollar rate "
                f"({est.units or est.note}); cannot enforce a budget"
            )
        total += est.usd
    return round(total, 4)


def run_suite_on_hardware(
    root: Path,
    adapter: HardwareAdapter,
    *,
    max_cost: float = 0.0,
    dry_run: bool = False,
) -> tuple[SuiteResult, float]:
    """Estimate, enforce the budget, then run every discovered test on hardware.

    Returns ``(suite, estimated_usd)``. Snapshot comparisons are skipped:
    baselines are recorded under simulator noise and would spuriously fail
    against real-device distributions.
    """
    items = discover(root)
    built = [(item, item.test.build()) for item in items]
    estimated = estimate_hardware_cost(
        [(qc, item.test.shots) for item, qc in built], adapter.catalog_device
    )
    if estimated > max_cost:
        raise SpendGuardError(
            f"estimated cost ${estimated:,.2f} on {adapter.target} exceeds the "
            f"--max-cost budget ${max_cost:,.2f}; nothing was submitted. "
            f"Re-run with --max-cost {estimated:,.2f} or higher to proceed."
        )

    suite = SuiteResult(tool_version=qontinuum.__version__)
    if dry_run:
        return suite, estimated

    for item, circuit in built:
        test = item.test
        result = TestResult(
            id=item.id,
            status=Status.PASS,
            backend=f"hw:{adapter.target}",
            shots=test.shots,
        )
        start = time.perf_counter()
        try:
            counts = adapter.submit(circuit, test.shots)
        except Exception as exc:
            result.status = Status.ERROR
            result.error = f"{type(exc).__name__}: {exc}"
            suite.tests.append(result)
            continue
        run = RunResult(
            counts=counts,
            shots=test.shots,
            backend=result.backend,
            circuit_hash=circuit_hash(circuit),
            duration_ms=(time.perf_counter() - start) * 1000,
        )
        result.circuit_hash = run.circuit_hash
        result.counts = run.counts
        result.duration_ms = round(run.duration_ms, 3)
        for check_fn in test.checks:
            result.checks.append(_evaluate(check_fn.__name__, partial(check_fn, run)))
        statuses = {c.status for c in result.checks}
        if Status.ERROR in statuses:
            result.status = Status.ERROR
        elif Status.FAIL in statuses:
            result.status = Status.FAIL
        suite.tests.append(result)
    return suite, estimated
