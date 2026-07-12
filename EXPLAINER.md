# Qontinuum, explained

*The quantum DevOps platform: pytest + Infracost + Datadog for quantum programs.*

---

## The problem, in one paragraph

A quantum program doesn't return a value — it returns **samples from a probability
distribution**, produced by hardware whose error rates drift daily, rented from vendors
whose prices for the *same job* differ by **two orders of magnitude** (a 200k-shot VQE
job: ~$85 on Rigetti, ~$6,000 on IonQ). Every tool in the classical delivery pipeline —
test runners, CI assertions, cost controls, monitoring — silently assumes deterministic
outputs and predictable pricing. So quantum teams ship by eyeballing histograms in
notebooks, discover cost overruns on the invoice, and find regressions when a demo
breaks. Qontinuum is the missing delivery pipeline, built quantum-native from the
statistics up.

## What it is

One Python package (`pip install qontinuum`), one CLI (`qont`), one GitHub Action.
Open source, Apache-2.0, no accounts or cloud required for the core workflow —
everything runs locally on simulators, including simulation of *real device noise*
from IBM's published calibration data.

```
┌─────────────────────────────────────────────────────────────────┐
│                    your quantum code (q_test_*.py)              │
├─────────────────────────────────────────────────────────────────┤
│  qont test      statistical regression testing (local, free)    │
│  qont cost      price the suite across every cloud provider     │
│  qont route     pick hardware: success probability × price      │
│  qont run       execute on real QPUs behind a spend cap         │
│  qont ci        all of it, as one CI step + PR comment          │
│  qont dashboard observability: trends, thresholds, cost         │
│  qont diff/hash semantic circuit versioning                     │
└─────────────────────────────────────────────────────────────────┘
```

## What it can do

### 1. Test quantum programs like software (`qont test`)

Write tests the pytest way — a decorated circuit factory plus checks:

```python
from qiskit import QuantumCircuit
from qontinuum import qtest, assert_distribution

@qtest(shots=4000)
def bell_pair():
    qc = QuantumCircuit(2)
    qc.h(0); qc.cx(0, 1); qc.measure_all()
    return qc

@bell_pair.check
def is_maximally_entangled(result):
    assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.05)
```

The assertion library speaks statistics, because equality can't work on samples:
total variation distance, chi-squared goodness-of-fit, Hellinger fidelity,
per-outcome probability bounds, and two-sample homogeneity tests against recorded
baselines ("snapshot testing", exactly like Jest — stale snapshots are detected by
circuit content hash and must be reviewed and re-recorded).

### 2. Refuse to be flaky — the statistical soundness floor

The flagship idea: **a threshold below the sampling noise floor is a bug in the
test, not the circuit.** Even a perfect device shows TVD > 0 at finite shots. Every
assertion knows the math (`floor = sqrt(((k+1)·ln2 − ln δ) / 2n)`) and refuses to
run a test that a perfect result would fail by chance — telling you exactly how many
shots would make it sound:

```
! tvd_threshold=0.01 is below the sampling noise floor 0.0289 at 4000 shots:
  even a perfect result would fail ~1% of the time.
  Use at least 33380 shots or raise the threshold to >= 0.0289.
```

### 3. Test against real hardware noise, offline and free

`backend="ibm:manila"` runs your circuit through an Aer noise model built from a
real IBM device's calibration snapshot (gate errors, readout errors, T1/T2) — no
account, no network, CI-safe. `backend="ibm:brisbane@live"` opts into *today's*
calibration via a free IBM account. Your CI can answer "does my circuit still
survive realistic noise?" on every push, for $0.

### 4. Know the price before you pay it (`qont cost`)

A data-driven catalog encodes each provider's actual pricing *model* — Braket's
per-task + per-shot, IBM's per-second runtime, Azure's per-gate-shot formulas,
Quantinuum's HQC credits — every figure carrying a verification date and source URL.
Prices your whole suite in one table, cheapest first. Devices without public dollar
rates are shown in native credits, never guessed.

### 5. Choose hardware rationally (`qont route`)

Combines cost with an estimated per-shot success probability (vendor error rates ×
gate counts, with a routing-overhead multiplier for sparse topologies) and ranks by
`--optimize cost`, `fidelity`, or `value` ($ per successful shot batch). Resolves
the cheap-but-noisy vs pricey-but-clean question with one number.

### 6. Run on real QPUs without surprise bills (`qont run`)

Adapters for IBM Quantum (Qiskit Runtime) and AWS Braket submit your suite to real
hardware — behind an **all-or-nothing spend guard**. The entire suite is priced
before the first shot is submitted; if the estimate exceeds `--max-cost`, nothing
runs. The default budget is $0: spending is always an explicit decision.

### 7. Put it all on every pull request (GitHub Action)

```yaml
- uses: XTanishkX/quantum/action@main
```

One sticky PR comment, updated in place: pass/fail per statistical check, what went
wrong with the actual statistics, and "running this suite on hardware: Rigetti $10.00
/ IBM $16.01 / IonQ $1,601.50." Cost review becomes part of code review.

### 8. Watch your suite drift over time (`qont dashboard`)

Every run appends to `.qontinuum/history.jsonl` (statistics captured even on *pass*,
so healthy suites chart too). `qont dashboard` renders a single self-contained HTML
file — status timeline, every check's statistic trending against its dashed
threshold, shots and cost per run. No server, no JavaScript dependencies; works as a
CI artifact.

### 9. Version circuits by meaning, not text (`qont hash` / `qont diff`)

Circuits are content-addressed by a canonical form that ignores register names,
circuit names, metadata, and QASM formatting — so `qont diff` shows only semantic
changes (`- cx q[0, 1]` / `+ cx q[1, 0]`), and the same canonicalization powers
snapshot staleness detection and result caching.

### 10. Bring your own SDK

`load_circuit` accepts Qiskit circuits, QASM 2/3 strings and files, **Cirq**
circuits, and **PennyLane** tapes (converted via their QASM exporters, no hard
dependency on either).

## How it's different (the USP)

| | Access platforms (qBraid, Strangeworks) | Benchmark suites (Benchpress, MQT) | Generic MLOps (MLflow) | **Qontinuum** |
|---|---|---|---|---|
| Job | sell QPU access | measure frameworks | log experiments | **ship quantum code safely** |
| Regression testing | — | — | manual | **statistical, shots-aware, in CI** |
| Cost intelligence | invoice after | — | — | **estimated before, on the PR** |
| Hardware choice | catalog browsing | — | — | **ranked by success × price** |
| Spend control | — | — | — | **all-or-nothing budget guard** |
| Works offline/free | ✗ (accounts) | ✓ | ✓ | **✓ incl. real-noise simulation** |

Four ideas nobody else has packaged:

1. **The statistical soundness floor.** Tools either assert naively or leave
   statistics to the user. Qontinuum computes whether your test *can* be sound at
   your shot count, and refuses to be flaky by construction.
2. **Infracost for quantum.** Pre-run, multi-provider price estimates as a PR
   comment — turning a 100× price spread from a billing surprise into a review item.
3. **Noise-aware CI with zero accounts.** Real calibration data → local noise model →
   every push tested against realistic hardware error, free.
4. **The $0-default spend guard.** Real-hardware execution where spending is opt-in
   per invocation, priced for the whole suite before anything is submitted.

## Production notes

- **Versioned contracts**: run results (`SCHEMA_VERSION`), snapshots, history
  records, and the circuit canonical form are all explicitly versioned.
- **Data over code**: adding a device or provider is a YAML entry, not a code change.
- **Tested**: 138 tests including hand-computed statistical fixtures and
  cross-checked pricing math; CI on Python 3.11/3.12/3.13; the repo's own PRs run
  Qontinuum on itself.
- **Releases**: tag → GitHub Actions → PyPI via trusted publishing (no secrets).

## v0.2: the full toolchain

Version 0.2 grew the surface from 10 commands to **110**, organized git-style
(`qont <noun> <verb>`), all documented in the
[command reference](https://xtanishkx.github.io/quantum/docs/commands/). The
headline additions, each a DevOps prevalent-practice translated to quantum:
**`qont lint`** (ruff-style rules for quantum-test footguns, including a static
statistical-soundness check), **`qont noise headroom`** (load testing: the noise
scale where your test breaks), **`qont history bisect`** (git-bisect over run
history), **`qont budget`** (FinOps caps enforced pre-submission),
**`qont test --cached`** (content-addressed simulation caching), **`qont fuzz`**
(empirical flakiness rates), **`qont pack`** (verifiable reproducibility
bundles), **`qont shots plan`** (suite-wide shot-count audits), and
**`qont report junit`** (native rendering in any CI system).

## Where it's going

The OSS core is the wedge. The platform roadmap: a hosted dashboard ("the cloud") that
ingests `history.jsonl` from many repos/teams — fleet-wide fidelity and spend trends,
org-level budgets, calibration-drift alerts; deeper transpilation-aware cost models;
scheduled hardware regression runs; more providers as their pricing goes public.
