# The statistics behind Qontinuum's assertions

## Why classical asserts don't work

A quantum circuit's output is a sample from a probability distribution. Run a perfect
Bell pair for 4,000 shots twice and you might get `{"00": 2013, "11": 1987}` and then
`{"00": 1979, "11": 2021}`. Equality checks fail; naive "within 1%" checks are either
too loose to catch bugs or too tight to survive shot noise. Regression testing quantum
programs is a *statistics* problem.

## Total variation distance with a soundness floor

`assert_distribution(result, expected, tvd_threshold=0.05)` computes the total
variation distance between the empirical distribution `p̂` and the expected
distribution `p`:

```
TVD(p̂, p) = ½ Σ_k |p̂(k) − p(k)|
```

Finite sampling makes TVD > 0 even for a perfect device. By a union bound over the
2^k events of a k-outcome distribution:

```
P(TVD ≥ ε) ≤ 2^(k+1) · exp(−2 n ε²)
```

so with confidence 1 − δ the sampled TVD stays below

```
floor = sqrt( ((k+1)·ln2 − ln δ) / (2n) )
```

If your threshold is *below* this floor, the assertion raises
`StatisticallyUnsoundError` instead of running: the test would fail on a perfect
device with probability up to δ — flaky by construction. The error message includes
the minimum shot count that makes your threshold sound
(`shots ≥ ((k+1)·ln2 − ln δ) / (2·threshold²)`).

Example: 2 outcomes, 4,000 shots, 99% confidence → floor ≈ 0.029. A `tvd_threshold`
of 0.05 is sound; 0.01 is not (needs ≥ 33,380 shots).

## Chi-squared goodness of fit

`assert_chi_squared(result, expected, alpha=0.01)` runs Pearson's test against the
expected probabilities. Outcomes observed *outside* the expected support have expected
probability zero, which the test cannot price — by default any such observation fails
the assertion. Under hardware noise, set `unexpected_tolerance` to the fraction of
stray shots you accept.

## Hellinger fidelity

`assert_fidelity` uses the squared Bhattacharyya coefficient
`F = (Σ_k √(p̂(k)·p(k)))²` — the classical fidelity commonly reported in quantum
benchmarking. Less sensitive to many-small-outcome noise than TVD; good for "is this
still recognizably the right state" checks under noise models.

## Two-sample tests for snapshots

Snapshot baselines are themselves finite samples, so comparing a new run to a baseline
is a *two-sample* problem: `assert_matches_baseline` builds the 2×K contingency table
and applies a chi-squared homogeneity test. Statistical power scales with both sample
sizes — a 2% drift is invisible at 200 shots and decisive at 200,000 — which is the
correct behavior: you buy sensitivity with shots.
