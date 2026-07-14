# Execution intelligence

Running a quantum program is an engineering decision, not a coin flip. The same
circuit on a different device can cost 100× more, run 10× slower, or return
noise instead of signal. Qontinuum's execution-intelligence layer turns the
evidence it already has — the cost catalog, published calibration quality, and
your local run history — into **explainable recommendations and plans**.

It is rule-based, provider-agnostic (it reads the plugin-extensible catalog, not
hardcoded providers), and fully offline. No AI model is required or used; every
number is traceable to its source, and missing evidence lowers confidence
rather than being invented.

```
qont recommend   # rank devices for a workload, with reasons
qont plan        # commit to one device + fallbacks (a pre-execution decision)
qont health      # per-device reliability from calibration + history
```

## The engine

The core lives in `qontinuum.intelligence` as pure functions over
already-gathered inputs — no CLI, no I/O — so it is easy to test and reuse from
reports, the planner, and (later) a hosted platform.

| Module | Responsibility |
|---|---|
| `health` | Blend catalog calibration and local history into a per-device reliability score, with confidence and attribution. |
| `recommend` | Rank devices for a workload under a strategy; attach an `Explanation` to every candidate. |
| `planning` | Turn a ranking into a concrete `ExecutionPlan` (selection + estimates + risks + fallbacks). |
| `analytics` | Aggregate history into engineering signals (provider usage, success rates, cost/fidelity trends). |
| `models` | The structured, presentation-free outputs every layer consumes. |

It builds directly on the existing router (`qontinuum.router`), which already
scores devices by per-shot success probability × cost, and the cost estimator —
execution intelligence adds runtime estimation, provider health, risk analysis,
and strategy-aware ranking on top.

## Strategies

`--strategy` (`-s`) chooses what to optimize:

| Strategy | Optimizes for |
|---|---|
| `cost` | lowest estimated dollar cost |
| `fidelity` | highest expected per-shot success |
| `speed` | fastest estimated runtime (queue time excluded) |
| `value` | dollars per successful shot |
| `reliability` | best composite of calibration + track record |
| `balanced` *(default)* | a weighted blend of fidelity, value, reliability, and speed |

Add `--budget <usd>` to any of them to exclude devices whose estimated cost
exceeds the cap before ranking.

```console
$ qont recommend examples --strategy fidelity
$ qont recommend examples --strategy value --budget 5
$ qont plan examples --strategy balanced
```

## Explainability

The engine never returns a score without the reasoning behind it. Every
recommendation and plan carries an `Explanation`:

- **summary** — the one-line verdict
- **reasons** — why this device leads under the chosen strategy
- **assumptions** — e.g. "expected success is a per-shot survival estimate from
  median error rates, not a measured fidelity"
- **missing** — evidence the engine did *not* have (no dollar rate, no history,
  stale calibration)
- **confidence** — 0–1, driven by how much evidence backed the assessment

```console
$ qont plan examples --strategy cost
...
Why: Rigetti Cepheus is the cost pick for this workload.
  • lowest estimated cost ($10.00)
  • reliability 94% (catalog)
  • estimated runtime ~24s (queue time not modeled)
  assumes: expected success is a per-shot survival estimate ...
  confidence: 70%
```

## Provider health

`qont health` reports, per catalog device:

- **calibration quality** — a 0–1 two-qubit + readout survival proxy from the
  catalog's published median error rates (always available, offline)
- **empirical success** — the pass rate of your local hardware runs on that
  device (from `.qontinuum/history.jsonl`, once you have ≥3 runs)
- **reliability** — a composite that weights history against the calibration
  prior by how many runs back it
- **evidence** and **confidence** — exactly which sources informed the row

When a signal is missing it stays blank and confidence drops — health degrades
gracefully rather than fabricating a number. As you accumulate hardware runs,
reliability shifts from a pure calibration estimate toward your measured
track record.

## Execution plans

`qont plan` produces a concrete decision: the selected provider and device, its
estimated runtime, cost, and expected fidelity, the risks going in, and ordered
fallbacks with the reason each lost to the primary. This is the foundation the
future intelligent-deployment layer will act on. If nothing fits the workload
(or the budget), planning fails cleanly with the reason.

## Programmatic use

```python
from qontinuum.cost import estimate_suite, load_catalog, profile_circuit
from qontinuum.intelligence import assess_health, recommend, build_plan, Strategy

catalog = load_catalog()
profiles = [profile_circuit(qc)]
estimates = estimate_suite([(qc, 2000)])
health = assess_health(catalog)            # add read_history(root) for empirical data

recs = recommend(profiles, [2000], estimates, catalog,
                 strategy=Strategy.BALANCED, health=health)
plan = build_plan(recs, strategy=Strategy.BALANCED, workload="my_suite")
print(plan.display, plan.estimated_cost_usd, plan.explanation.summary)
```
