# Changelog

All notable changes to Qontinuum are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow
[Semantic Versioning](https://semver.org/) (pre-1.0: minor bumps may break).

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
