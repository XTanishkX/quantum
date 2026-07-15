# Contributing to Qontinuum

## Development setup

```sh
git clone https://github.com/XTanishkX/quantum
cd quantum
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ibm]"
```

## Checks

```sh
ruff check .        # lint
pytest              # unit + integration tests
qont test examples  # dogfood the CLI
```

Both run in CI on every PR, along with the Qontinuum action itself running
against `examples/` (we eat our own cooking — quantum tests + cost comment).

## Project layout

| Path | What lives there |
|---|---|
| `src/qontinuum/circuits` | QASM/Qiskit/Cirq/PennyLane loading, canonical form, hashing, semantic diff |
| `src/qontinuum/assertions` | statistics (`stats.py`), user-facing asserts, statistic capture context |
| `src/qontinuum/runner` | `@qtest`, discovery, backends, engine, snapshots |
| `src/qontinuum/noise` | Aer noise models from IBM calibration data |
| `src/qontinuum/cost` | pricing catalog (`catalog.yaml`), circuit profiling, estimator |
| `src/qontinuum/router` | device scoring: success probability × cost, ranking strategies |
| `src/qontinuum/hardware` | real-QPU adapters (IBM, Braket) behind the all-or-nothing spend guard |
| `src/qontinuum/plugins` | plugin protocols + registry; the built-in providers/backends/SDKs |
| `src/qontinuum/intelligence` | execution intelligence: provider health, recommendation engine, planner, analytics (pure, provider-agnostic) |
| `src/qontinuum/telemetry` | opt-in Quantum Intelligence Network: consent, privacy scrubber, outbox, HTTPS sync, community cache |
| `src/qontinuum/report` | versioned JSON schema, markdown renderer, run history, HTML dashboard |
| `action/` | the composite GitHub Action |

## Design rules

- **The result JSON schema is a contract.** Anything that changes its shape bumps
  `SCHEMA_VERSION` in `report/schema.py`.
- **Pricing lives in data, not code.** New devices/providers are added to
  `cost/catalog.yaml` with a source URL and verified date; the estimator only knows
  pricing *models* (`per_shot`, `per_second`, `gate_shot`, `hqc`).
- **Assertions must be shots-aware.** Any new statistical assertion needs a soundness
  guard: it must refuse configurations that would be flaky by construction.
- **Offline by default.** Tests and CI must run without accounts or network; anything
  live (e.g. `@live` calibration) is opt-in.
- **The edges are plugins, the IR is Qiskit.** New providers, simulator backends, and
  source SDKs are added as plugins in the `qontinuum.{providers,backends,sdks}`
  entry-point groups — in-tree via `plugins/builtins.py`, or shipped as a separate
  package. Core code speaks one IR (`QuantumCircuit`); don't add SDK-specific branches
  to the runner. See [`docs/plugins.md`](docs/plugins.md).
