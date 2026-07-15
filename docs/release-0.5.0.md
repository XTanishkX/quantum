# Qontinuum 0.5.0 — the public beta

This is the release where Qontinuum becomes a complete **Quantum Engineering
Platform**: a single tool to build, test, benchmark, cost, plan, run, observe,
and continuously improve quantum software across providers. It is fully
backwards compatible — `pip install -U qontinuum`.

## Quantum Intelligence Network

The headline: an **optional**, privacy-preserving way to pool *anonymous
engineering metadata* so recommendations improve for everyone. It is **off by
default** and Qontinuum remains fully functional offline forever.

- **Opt-in and transparent.** `qont telemetry enable` states exactly what is
  shared; `qont telemetry preview` shows the literal payload.
- **Anonymous by construction.** Only an allowlist of engineering metadata can
  leave the machine — public provider/device ids, outcome, runtime, queue, cost,
  bucketed shots. Circuits, distributions, counts, snapshots, source,
  credentials, and identity have **no field** and are never built.
- **Offline-first & safe.** Records queue locally with integrity signing and
  only leave on an explicit HTTPS `sync`; any failure keeps the queue intact.
  Community snapshots are validated before they can influence a recommendation.

See [Quantum Intelligence Network](intelligence-network.md) and
[Privacy](privacy.md).

## A complete execution planner

`qont plan` now produces a fully reasoned pre-execution decision: selected and
alternative backends, expected runtime, **expected queue**, expected cost and
fidelity, an **execution risk level**, **confidence**, and fallbacks. This is the
foundation for future automated deployment.

## The engineering report

`qont report engineering` ties the whole intelligence layer into one document —
recommendation, execution plan (with risk and confidence), provider analysis,
cost analysis, and historical context — reusing the exact engine behind
`recommend` / `plan` / `health`. See [Reporting](reporting.md).

## Security & privacy, documented

New [Security](security.md) and [Privacy](privacy.md) pages document secure
defaults: telemetry off, HTTPS-only egress, allowlist payloads, schema-validated
inputs, no dynamic code execution, and defensive plugin isolation.

## Upgrade notes

No breaking changes. New capabilities are additive and opt-in:

- Telemetry is disabled unless you run `qont telemetry enable`.
- `assess_health`, `recommend`, and `qont health` gain an optional community
  signal, used only when a snapshot has been synced.
- `ExecutionPlan` gained queue/risk/confidence fields; existing consumers are
  unaffected.

## What's next

Beta feedback, deeper deployment automation on top of the planner, and — if the
community wants it — a hosted aggregation endpoint for the intelligence network
(the client already speaks a documented, host-agnostic contract).
