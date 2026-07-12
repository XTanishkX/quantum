"""User-facing assertions for quantum measurement results.

All assertions accept either a ``RunResult`` or a raw ``dict[str, int]`` of
counts, raise :class:`QuantumAssertionError` on failure, and raise
:class:`StatisticallyUnsoundError` when the requested tolerance cannot be
resolved at the available shot count (a test-configuration bug, not a
regression).
"""

from __future__ import annotations

from typing import Any

from qontinuum.assertions import stats
from qontinuum.assertions.context import record


class QuantumAssertionError(AssertionError):
    """A statistical check on measurement results failed."""

    def __init__(self, message: str, *, statistic: float | None = None,
                 threshold: float | None = None):
        super().__init__(message)
        self.statistic = statistic
        self.threshold = threshold


class StatisticallyUnsoundError(RuntimeError):
    """The assertion cannot distinguish signal from shot noise as configured."""


def _counts_of(result: Any) -> dict[str, int]:
    counts = result.counts if hasattr(result, "counts") else result
    if not isinstance(counts, dict):
        raise TypeError(f"expected RunResult or counts dict, got {type(result).__name__}")
    return stats.normalize_counts(counts)


def assert_distribution(
    result: Any,
    expected: dict[str, float],
    *,
    tvd_threshold: float = 0.05,
    confidence: float = 0.99,
) -> None:
    """Assert the sampled distribution is within ``tvd_threshold`` TVD of ``expected``.

    Shots-aware: if ``tvd_threshold`` is below the sampling noise floor for
    this shot count, the test would be flaky by construction and a
    :class:`StatisticallyUnsoundError` is raised instead, with the minimum
    shot count that would make the threshold sound.
    """
    counts = _counts_of(result)
    expected = stats.validate_expected(expected)
    shots = sum(counts.values())
    value = stats.tvd(counts, expected)
    # Recorded before the soundness gate so linting and dashboards see the
    # threshold even for tests that are statistically unsound as configured.
    record("tvd", value, tvd_threshold)
    floor = stats.sampling_floor(len(expected), shots, confidence)
    if tvd_threshold < floor:
        needed = stats.shots_for_threshold(len(expected), tvd_threshold, confidence)
        raise StatisticallyUnsoundError(
            f"tvd_threshold={tvd_threshold:.4g} is below the sampling noise floor "
            f"{floor:.4g} at {shots} shots: even a perfect result would fail "
            f"~{100 * (1 - confidence):.0f}% of the time. Use at least {needed} shots "
            f"or raise the threshold to >= {floor:.4g}."
        )
    if value > tvd_threshold:
        top = sorted(counts.items(), key=lambda kv: -kv[1])[:4]
        observed = ", ".join(f"{k}: {v / shots:.3f}" for k, v in top)
        raise QuantumAssertionError(
            f"TVD {value:.4f} exceeds threshold {tvd_threshold} "
            f"({shots} shots; top observed: {observed})",
            statistic=value,
            threshold=tvd_threshold,
        )


def assert_chi_squared(
    result: Any,
    expected: dict[str, float],
    *,
    alpha: float = 0.01,
    unexpected_tolerance: float = 0.0,
) -> None:
    """Pearson goodness-of-fit: fail when the data rejects ``expected`` at ``alpha``.

    ``unexpected_tolerance`` is the tolerated fraction of shots observed on
    outcomes with expected probability zero (useful under hardware noise).
    """
    counts = _counts_of(result)
    expected = stats.validate_expected(expected)
    statistic, p_value = stats.chi_squared_pvalue(
        counts, expected, unexpected_tolerance=unexpected_tolerance
    )
    record("chi2_pvalue", p_value, alpha)
    if p_value < alpha:
        raise QuantumAssertionError(
            f"chi-squared test rejects the expected distribution "
            f"(statistic={statistic:.2f}, p={p_value:.2e} < alpha={alpha})",
            statistic=p_value,
            threshold=alpha,
        )


def assert_fidelity(
    result: Any,
    expected: dict[str, float],
    *,
    min_fidelity: float = 0.95,
) -> None:
    """Assert classical (Hellinger) fidelity against ``expected`` is high enough."""
    counts = _counts_of(result)
    expected = stats.validate_expected(expected)
    value = stats.hellinger_fidelity(counts, expected)
    record("fidelity", value, min_fidelity)
    if value < min_fidelity:
        raise QuantumAssertionError(
            f"fidelity {value:.4f} below minimum {min_fidelity}",
            statistic=value,
            threshold=min_fidelity,
        )


def assert_probability(
    result: Any,
    outcome: str,
    *,
    min_p: float = 0.0,
    max_p: float = 1.0,
) -> None:
    """Assert the estimated probability of one outcome lies within [min_p, max_p]."""
    counts = _counts_of(result)
    shots = sum(counts.values())
    p = counts.get(outcome.replace(" ", ""), 0) / shots
    record(f"P({outcome})", p, None)
    if not (min_p <= p <= max_p):
        raise QuantumAssertionError(
            f"P({outcome}) = {p:.4f} outside [{min_p}, {max_p}] ({shots} shots)",
            statistic=p,
        )


def assert_matches_baseline(
    result: Any,
    baseline: dict[str, int],
    *,
    alpha: float = 0.01,
) -> None:
    """Assert two sampled distributions are statistically indistinguishable.

    Used for snapshot comparison: both sides are finite samples, so this is a
    two-sample homogeneity test, not a comparison against exact probabilities.
    """
    counts = _counts_of(result)
    baseline = stats.normalize_counts(baseline)
    _, p_value = stats.two_sample_pvalue(counts, baseline)
    record("baseline_pvalue", p_value, alpha)
    if p_value < alpha:
        distance = stats.tvd_two_sample(counts, baseline)
        raise QuantumAssertionError(
            f"distribution drifted from baseline (two-sample chi-squared "
            f"p={p_value:.2e} < alpha={alpha}; empirical TVD {distance:.4f})",
            statistic=p_value,
            threshold=alpha,
        )
