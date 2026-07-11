# Launch notes (working draft — not published)

## Positioning

One-liner: **pytest + Infracost for quantum computing.**

The pitch, in the order that lands:

1. Quantum programs return probability distributions, not values. Nothing in the
   classical CI toolchain can regression-test that. (Problem people recognize.)
2. Qontinuum is a test runner where assertions are statistical tests — with a
   soundness guard that refuses statistically-flaky test configurations. (Novel core.)
3. Every PR gets a sticky comment: pass/fail + "this suite costs $6 on Rigetti,
   $961 on IonQ." (The screenshot that gets shared.)
4. Noise-aware mode simulates against real IBM calibration data, offline, free.

## Show HN draft

> **Show HN: Qontinuum – pytest + Infracost for quantum programs**
>
> Quantum programs don't return values — they return samples from a probability
> distribution, executed on hardware where the same job costs $6 on one vendor and
> $961 on another. I built Qontinuum to make both problems boring: a pytest-style
> runner whose assertions are statistical tests (TVD with shots-aware soundness
> floors, chi-squared, two-sample snapshot comparisons), and a GitHub Action that
> posts hardware cost estimates on every PR before you spend anything.
>
> Everything runs offline on simulators, including noise models built from real IBM
> device calibration snapshots. Apache-2.0, Python 3.11+.

## Channels

- Show HN (weekday morning US time)
- r/QuantumComputing, r/Python
- Qiskit Slack #general / #qiskit-ecosystem (mind community rules on self-promotion)
- Unitary Fund Discord (they fund exactly this category — also a microgrant candidate)

## Pre-launch checklist

- [ ] GitHub repo public with topics: quantum-computing, ci, testing, qiskit
- [ ] PyPI package published (trusted publishing configured)
- [ ] Action e2e-verified on a real PR (screenshot for README)
- [ ] README GIF of `qont test` + failing run
- [ ] Demo repo: small QAOA project using the action, with a PR showing the comment
