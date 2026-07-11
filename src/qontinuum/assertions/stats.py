"""Pure statistics on measurement-count distributions.

Everything here operates on plain ``dict[str, int]`` counts (bitstring ->
occurrences) and knows nothing about circuits or backends.
"""

from __future__ import annotations

import math

from scipy import stats as _scipy_stats


def normalize_counts(counts: dict[str, int]) -> dict[str, int]:
    """Normalize qiskit-style count keys (register spaces stripped) and merge."""
    out: dict[str, int] = {}
    for key, value in counts.items():
        k = key.replace(" ", "")
        out[k] = out.get(k, 0) + int(value)
    return out


def to_probs(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        raise ValueError("counts contain no shots")
    return {k: v / total for k, v in counts.items()}


def validate_expected(expected: dict[str, float]) -> dict[str, float]:
    """Check an expected distribution: probabilities in [0, 1] summing to ~1."""
    if not expected:
        raise ValueError("expected distribution is empty")
    cleaned = {k.replace(" ", ""): float(v) for k, v in expected.items()}
    if any(p < 0 or p > 1 for p in cleaned.values()):
        raise ValueError("expected probabilities must be within [0, 1]")
    total = sum(cleaned.values())
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(f"expected probabilities sum to {total:.6f}, not 1")
    return cleaned


def tvd(counts: dict[str, int], expected: dict[str, float]) -> float:
    """Total variation distance between the empirical and expected distributions."""
    probs = to_probs(counts)
    support = set(probs) | set(expected)
    return 0.5 * sum(abs(probs.get(k, 0.0) - expected.get(k, 0.0)) for k in support)


def tvd_two_sample(a: dict[str, int], b: dict[str, int]) -> float:
    """Total variation distance between two empirical distributions."""
    pa, pb = to_probs(a), to_probs(b)
    support = set(pa) | set(pb)
    return 0.5 * sum(abs(pa.get(k, 0.0) - pb.get(k, 0.0)) for k in support)


def hellinger_fidelity(counts: dict[str, int], expected: dict[str, float]) -> float:
    """Classical fidelity (squared Bhattacharyya coefficient) vs an expected distribution."""
    probs = to_probs(counts)
    support = set(probs) | set(expected)
    bc = sum(math.sqrt(probs.get(k, 0.0) * expected.get(k, 0.0)) for k in support)
    return bc * bc


def sampling_floor(num_outcomes: int, shots: int, confidence: float = 0.99) -> float:
    """Smallest TVD threshold that finite sampling can reliably resolve.

    Even a perfect device produces TVD > 0 against the true distribution
    because of shot noise. By a union bound over the 2^k events of a
    k-outcome distribution, ``P(TVD >= eps) <= 2^(k+1) * exp(-2 n eps^2)``,
    so with probability >= ``confidence`` the sampled TVD stays below the
    value returned here. Thresholds below this floor make a test flaky by
    construction.
    """
    if shots <= 0:
        raise ValueError("shots must be positive")
    k = max(2, num_outcomes)
    delta = 1.0 - confidence
    return math.sqrt(((k + 1) * math.log(2) - math.log(delta)) / (2 * shots))


def shots_for_threshold(num_outcomes: int, threshold: float, confidence: float = 0.99) -> int:
    """Minimum shots so that ``sampling_floor(...) <= threshold``."""
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    k = max(2, num_outcomes)
    delta = 1.0 - confidence
    return math.ceil(((k + 1) * math.log(2) - math.log(delta)) / (2 * threshold**2))


def chi_squared_pvalue(
    counts: dict[str, int],
    expected: dict[str, float],
    *,
    unexpected_tolerance: float = 0.0,
) -> tuple[float, float]:
    """Pearson goodness-of-fit test of counts against an expected distribution.

    Returns ``(statistic, p_value)``. Outcomes observed outside the expected
    support first get checked against ``unexpected_tolerance`` (as a fraction
    of total shots); beyond it the test fails outright (p-value 0) since the
    expected probability there is zero.
    """
    probs_support = {k: p for k, p in expected.items() if p > 0}
    total = sum(counts.values())
    unexpected = sum(v for k, v in counts.items() if k not in probs_support)
    if unexpected > unexpected_tolerance * total:
        return math.inf, 0.0

    observed = [counts.get(k, 0) for k in probs_support]
    n_support = sum(observed)
    if n_support == 0:
        return math.inf, 0.0
    weight = sum(probs_support.values())
    f_exp = [p / weight * n_support for p in probs_support.values()]
    statistic, p_value = _scipy_stats.chisquare(observed, f_exp)
    return float(statistic), float(p_value)


def two_sample_pvalue(a: dict[str, int], b: dict[str, int]) -> tuple[float, float]:
    """Homogeneity test: were two sets of counts drawn from the same distribution?

    Chi-squared test on the 2xK contingency table over the union support.
    Returns ``(statistic, p_value)``.
    """
    support = sorted(set(a) | set(b))
    table = [
        [a.get(k, 0) for k in support],
        [b.get(k, 0) for k in support],
    ]
    # Drop outcomes absent from both samples (all-zero columns break the test).
    cols = [i for i in range(len(support)) if table[0][i] + table[1][i] > 0]
    table = [[row[i] for i in cols] for row in table]
    if len(table[0]) < 2:
        return 0.0, 1.0  # identical single-outcome distributions
    result = _scipy_stats.chi2_contingency(table)
    return float(result.statistic), float(result.pvalue)
