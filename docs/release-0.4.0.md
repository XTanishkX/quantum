# Qontinuum 0.4.0 — "Execution Intelligence"

**Qontinuum grows from a quantum DevOps toolchain into the Quantum Engineering
Platform.** This release teaches it to *reason* about executions — not just run
them — and lands two architectural foundations underneath: a provider/SDK plugin
system and a versioned execution history database.

Everything here is backwards compatible: no public signature, spec string, or
result-JSON key changed. `pip install -U qontinuum`.

## Execution intelligence

Running a circuit is an engineering decision. The same job can cost 100× more,
run 10× slower, or return noise instead of signal on the wrong device. Three new
commands turn the evidence Qontinuum already has — the cost catalog, published
calibration, and your local run history — into ranked, **explained** decisions:

- **`qont recommend`** — rank devices for your workload under six strategies
  (`cost`, `fidelity`, `speed`, `value`, `reliability`, `balanced`), with
  `--budget` filtering. Every candidate carries the reasoning, assumptions,
  missing evidence, and a confidence score behind it.
- **`qont plan`** — a concrete pre-execution plan: selected device, estimated
  runtime/cost/fidelity, risks, and ordered fallbacks.
- **`qont health`** — per-device reliability blending calibration quality with
  your local hardware track record, always attributed and confidence-weighted.

It is rule-based, provider-agnostic, and fully offline — no AI model, no
hardcoded vendors. See [Execution intelligence](execution-intelligence.md).

## Provider, backend & SDK plugins

Providers, simulator backends, and SDKs are now **plugins**. `ibm`, `braket`,
`aer`, `qiskit`, `cirq`, and `pennylane` ship built in; anyone can add a new
provider or SDK by installing a package that declares an entry point — no fork,
no core changes. `qont plugin list / show / doctor` inspect and diagnose them.
See [Extending Qontinuum](plugins.md).

## Versioned execution history & richer dashboards

The local history is now a **versioned execution database**: old lines are
migrated up on read (so any prior file stays valid), and hardware runs record a
structured `execution` block — provider, cost, runtime, routing strategy,
outcome — designed as the ingestion format a future hosted platform consumes
without a redesign. `qont dashboard` gains hardware cost-over-time, provider
usage, and provider-comparison views, still as a single self-contained HTML
file. See [Observability](observability.md).

## Upgrade notes

- No breaking changes. `qont history stats` gains fields (old JSON keys kept).
- `append_history` gained an optional `execution=` argument; existing callers
  are unaffected.
- `qontinuum.__version__` now correctly reports the release version.

## What's next

Deeper deployment intelligence (queue-time modelling, actual-vs-estimated cost
variance) and, later, an opt-in privacy-respecting cloud that turns anonymous
execution metadata into community hardware analytics. Telemetry stays off by
default.
