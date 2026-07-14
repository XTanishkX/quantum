# Changelog

All notable changes to Qontinuum are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow
[Semantic Versioning](https://semver.org/) (pre-1.0: minor bumps may break).

## [Unreleased] — 0.4.0 "Execution Intelligence" (in progress)

Qontinuum starts to *reason* about executions, not just run them. A new
rule-based, provider-agnostic, fully-offline intelligence layer turns the
evidence already on hand — the cost catalog, published calibration quality, and
local run history — into explainable recommendations and plans.

### Added — `qontinuum.intelligence`

- **Recommendation engine** — ranks devices for a workload under six
  strategies (`cost`, `fidelity`, `speed`, `value`, `reliability`, `balanced`),
  with optional `--budget` filtering. Builds on the existing router scoring and
  adds runtime estimation, provider-health reliability, and risk analysis.
- **Provider health** — a per-device reliability score blending catalog
  calibration quality with the empirical success rate of your local hardware
  runs, always attributed (evidence + confidence) and degrading gracefully when
  data is missing.
- **Execution planning** — turns a ranking into a concrete `ExecutionPlan`:
  selected device, estimated runtime/cost/fidelity, risks, and ordered
  fallbacks. Fails cleanly when nothing fits the workload or budget.
- **Explainability** — every recommendation and plan carries an `Explanation`
  (summary, reasons, assumptions, missing evidence, confidence). The engine
  never returns a score without the reasoning behind it.
- **Analytics** — a history-aggregation core (provider usage, hardware success
  rate, cost/fidelity trends) that powers reporting and future dashboards.

### Added — CLI

- **`qont recommend`** — ranked hardware for the discovered workload, with the
  top choice explained and runners-up noted.
- **`qont plan`** — a pre-execution plan with estimates, risks, and fallbacks.
- **`qont health`** — the provider-health table.

### Changed

- **`qont history stats`** gains execution analytics (hardware run count,
  hardware success rate, per-provider usage). Existing JSON keys are preserved.

## [0.3.0] — 2026-07-15

The "open platform" release: providers, simulator backends, and SDKs are now
**plugins**. Anyone can `pip install` a package that adds a new provider or SDK
and `qont` discovers it automatically — no fork, no core changes.

### Added — plugin system

- **`qontinuum.plugins`** — three extension points, each a small typed
  `Protocol`: `ProviderPlugin` (hardware execution), `BackendPlugin` (local
  simulation), `SDKPlugin` (foreign circuit → Qiskit IR). A hybrid registry
  discovers built-ins (always present) plus third-party plugins declared in the
  `qontinuum.providers` / `qontinuum.backends` / `qontinuum.sdks` entry-point
  groups. A broken or misdeclared plugin is recorded as unavailable with its
  error and never crashes discovery or the CLI.
- **`qont plugin`** — `list` (every discovered plugin, source, availability),
  `show <name>` (full detail + implementation path), and `doctor` (health
  check with exact `pip install` hints; non-zero exit only when a *built-in*
  fails to load).
- **Provider catalog contribution** — a provider plugin may implement
  `catalog_fragment()` to ship execution *and* pricing/routing-quality data for
  its devices as one package; `load_catalog()` merges these additively (bundled
  devices always win a collision).

### Changed

- Provider resolution (`resolve_adapter`), backend resolution
  (`resolve_backend`), and circuit loading (`load_circuit`) now route through
  the plugin registry instead of hardcoded `if/elif` branches. **Fully
  backwards compatible** — every public signature, spec string, and error type
  is preserved; `ibm`/`braket`/`aer`/`qiskit`/`cirq`/`pennylane` are the
  built-in plugins.

### Fixed

- `qontinuum.__version__` was stuck at `0.1.0`; it now tracks the release
  version, so `qont version` reports correctly.

## [0.2.0] — 2026-07-12

The "complete toolchain" release: from 10 commands to **110**, organized into
git-style groups, plus production hardening throughout.

### Added — new command groups

- **`qont lint`** — ruff for quantum tests: rules Q001–Q009 (statistical
  soundness floor, missing measurements, idle qubits, unbound parameters,
  depth vs noise, missing snapshot baselines, multiple-testing, @live network
  dependence, trivial shot counts), with `--select/--ignore` and per-rule
  explanations.
- **`qont noise`** — noise as a load-testing axis: `sweep` a test across scaled
  device noise, `headroom` binary-searches the noise level where it breaks,
  `inject` runs explicit synthetic error rates.
- **`qont budget`** — QPU FinOps: monthly/total caps enforced before hardware
  submission, spend ledger, naive forecast.
- **`qont cache`** — content-addressed simulation result cache; `qont test
  --cached` skips unchanged seeded circuits.
- **`qont history`** — `compare` runs statistically and `bisect` (git-bisect
  for quantum: which run first crossed the threshold), plus list/show/stats/
  export/prune.
- **`qont bench`** — mirror-circuit survival, RB-lite decay fits, QV-style
  estimates, cross-backend `suite` and `compare`.
- **`qont pack`** — reproducibility bundles: suite + baselines + seeded results
  + environment lock; `verify` re-runs and two-sample-compares.
- **`qont registry`** — named circuit lineage with content-hash versions/tags.
- **`qont circuit`** — show/stats/canon/convert/transpile-delta/unitary
  equiv/mirror/random.
- **`qont device`** — catalog cards, comparisons, topology sketches, per-qubit
  calibration tables, live drift reports, queue depth, `best` router shortcut.
- **`qont shots`** — the napkin math as commands: `for-tvd`, `floor`, `power`,
  and suite-wide `plan` audits.
- **`qont stats`** — describe/tvd/fidelity/chi2/entropy/compare on counts files.
- **`qont report`** — JUnit XML, SVG badge, markdown, PR comment, JSON, and a
  greppable one-line `summary`.
- **`qont fuzz`** (seed-sweep flakiness rates with Wilson intervals),
  **`qont explain`** (failure forensics), **`qont mock`** (synthetic counts),
  **`qont watch`** (re-run on change; poll live calibration).
- **`qont init` / `config` / `doctor` / `env` / `schedule` / `completion`** —
  project scaffolding, git-style config, environment diagnostics and locks,
  scheduled-workflow generators.

### Added — engine

- Assertions record their statistic via a capture context even when passing.
- `TestResult.cached` field (schema-compatible addition).
- Budget guard integrated into the hardware spend guard.

### Changed

- CLI help reorganized into panels; global `--version`; shell completion
  enabled; consistent `--json` and exit codes (0/1/2/3) across commands.

### Production

- `py.typed`, mypy and coverage gates in CI, issue/PR templates, SECURITY.md,
  CODE_OF_CONDUCT.md, mkdocs documentation site.

## [0.1.0] — 2026-07-12

Initial release: `qont test` (statistical assertions with soundness floors,
snapshot baselines), `qont cost` (multi-provider price estimates), `qont
route`, `qont run --max-cost`, `qont ci` + GitHub Action with sticky PR
comment, `qont dashboard`, `qont diff`/`hash`, IBM calibration noise models,
Cirq/PennyLane loading.
