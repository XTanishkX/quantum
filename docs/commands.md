# Command reference

All 124 commands. Every read command accepts `--json`; exit codes are `0` ok, `1` failures/findings, `2` usage/config, `3` guard refusal.

## Core & flat commands

| Command | What it does |
|---|---|
| `qont ci` | Run the suite and emit a markdown report (regressions + hardware cost). |
| `qont completion` | Show how to enable shell completion. |
| `qont cost` | Estimate what running the discovered tests on real hardware would cost. |
| `qont dashboard` | Render run history as a self-contained HTML dashboard. |
| `qont diff` | Semantic diff of two circuits (register names and formatting ignored). |
| `qont doctor` | Diagnose the environment: imports, extras, config, catalog freshness. |
| `qont explain` | Failure forensics: which outcomes drove a failing check, and why. |
| `qont fuzz` | Flakiness hunter: rerun the suite under a seed sweep, estimate pass rates. |
| `qont hash` | Print a circuit's canonical content hash. |
| `qont health` | Provider health: per-device reliability from calibration and local history. |
| `qont init` | Scaffold a Qontinuum project: example test, config, gitignore entries. |
| `qont mock` | Generate synthetic measurement counts (test fixtures, demos, docs). |
| `qont plan` | Produce a concrete execution plan: device, estimates, risks, fallbacks. |
| `qont recommend` | Rank hardware for the discovered workload and explain the top choice. |
| `qont route` | Recommend which hardware should run the discovered tests. |
| `qont run` | Run the discovered tests on REAL hardware, guarded by a spend cap. |
| `qont test` | Discover and run quantum tests (files matching q_test_*.py). |
| `qont version` | Print the qontinuum version. |

See [Execution intelligence](execution-intelligence.md) for `recommend`, `plan`,
and `health`.

## `qont bench`

Mirror, RB-lite, and QV-style benchmarks (estimates, labeled as such).

| Command | What it does |
|---|---|
| `qont bench compare` | Head-to-head: which backend treats your circuits better? |
| `qont bench mirror` | Mirror-circuit benchmark: run U·U†, measure survival of |0...0>. |
| `qont bench qv` | Quantum-volume-style estimate (heavy-output probability per width). |
| `qont bench rb` | RB-lite: exponential decay fit over mirrored random-layer circuits. |
| `qont bench suite` | The standard benchmark battery across several backends. |

## `qont budget`

Hardware spend budgets and the run ledger.

| Command | What it does |
|---|---|
| `qont budget forecast` | Project this month's spend from the current run cadence. |
| `qont budget ledger` | Recorded hardware-run spend entries. |
| `qont budget reset` | Clear the spend ledger (caps stay configured). |
| `qont budget set` | Set a spend cap that `qont run` enforces before submitting anything. |
| `qont budget show` | Current caps. |
| `qont budget status` | Spend vs caps, from the run ledger. |

## `qont cache`

Simulation result cache (seeded runs only).

| Command | What it does |
|---|---|
| `qont cache clear` | Delete every cached result. |
| `qont cache gc` | Garbage-collect old cache entries. |
| `qont cache ls` | List cached results. |
| `qont cache stats` | Cache size and entry count. |

## `qont circuit`

Inspect, convert, and generate circuits.

| Command | What it does |
|---|---|
| `qont circuit canon` | Print the versioned canonical form (what the content hash covers). |
| `qont circuit convert` | Convert between OpenQASM dialects (also accepts Cirq/PennyLane via API). |
| `qont circuit diff` | Semantic diff (same engine as top-level `qont diff`). |
| `qont circuit equiv` | True unitary equivalence via statevector (up to global phase, <=12 qubits). |
| `qont circuit hash` | Print the circuit's canonical content hash. |
| `qont circuit mirror` | Emit the mirror-benchmark circuit U·U†: ideal outcome is all zeros. |
| `qont circuit random` | Generate a reproducible random circuit (fuzzing / benchmarking input). |
| `qont circuit show` | Draw the circuit as unicode art. |
| `qont circuit stats` | Gate counts, depth, SPAM profile, and content hash. |
| `qont circuit transpile` | Show what the device will actually run: depth/gate deltas after targeting. |

## `qont config`

Project configuration (.qontinuum/config.toml).

| Command | What it does |
|---|---|
| `qont config edit` | Open the config file in $EDITOR. |
| `qont config get` | Print one config value (built-in default when unset). |
| `qont config list` | Show every known key: effective value, source, and description. |
| `qont config path` | Print the config file path. |
| `qont config set` | Set a config value. |
| `qont config unset` | Remove a key (reverts to the built-in default). |

## `qont device`

Browse, compare, and interrogate QPUs.

| Command | What it does |
|---|---|
| `qont device best` | Quick router: best devices for a qubit count and optional budget. |
| `qont device calib` | Per-qubit calibration table (T1/T2/readout) from bundled or @live data. |
| `qont device compare` | Two devices side by side. |
| `qont device drift` | Calibration weather report: today's live device vs the bundled snapshot. |
| `qont device list` | Every device in the pricing catalog. |
| `qont device queue` | Live queue depth for an IBM device (needs a saved account). |
| `qont device show` | Full catalog card for one device. |
| `qont device topology` | Sketch the qubit connectivity. |

## `qont env`

Environment capture for reproducibility.

| Command | What it does |
|---|---|
| `qont env diff` | Compare the current environment against the lock file. |
| `qont env lock` | Write .qontinuum/env.lock.json capturing the current environment. |
| `qont env show` | Print the execution environment relevant to reproducibility. |

## `qont history`

Query and mine the local run history.

| Command | What it does |
|---|---|
| `qont history bisect` | git-bisect for quantum: find the run where a check first went bad. |
| `qont history compare` | Statistic-level regression between two recorded runs. |
| `qont history export` | Export run summaries for spreadsheets or BI tools. |
| `qont history list` | Recent runs, newest last (run numbers are stable indices). |
| `qont history prune` | Trim history to the most recent N runs. |
| `qont history show` | Full detail of one run: every test and check with statistics. |
| `qont history stats` | Aggregate history: pass rate, flakiest test, shots and spend totals. |

## `qont lint`

Static + probe-based checks for quantum test suites (rules Q001-Q009). Bare `qont lint` scans the current directory; `qont lint check <path>` scans elsewhere.

| Command | What it does |
|---|---|
| `qont lint` | Scan the current directory when no subcommand is given. |
| `qont lint check` | Scan a specific path. Exit 1 on findings. |
| `qont lint explain` | Explain one rule: what it catches and how to fix it. |
| `qont lint rules` | List every lint rule. |

## `qont noise`

Noise models: inspect, sweep, and find headroom.

| Command | What it does |
|---|---|
| `qont noise headroom` | Load-testing for quantum: how much worse can the device get before this fails? |
| `qont noise inject` | Run one test under an explicit synthetic noise model. |
| `qont noise list` | Available noise sources. |
| `qont noise show` | The three-knob noise profile distilled from a device's calibration. |
| `qont noise sweep` | Run one test under progressively scaled device noise. |

## `qont pack`

Create and verify reproducibility bundles.

| Command | What it does |
|---|---|
| `qont pack create` | Bundle the suite, baselines, seeded results, and environment lock. |
| `qont pack inspect` | Show a pack's manifest: environment, files, suite summary. |
| `qont pack verify` | Re-run the packed suite in THIS environment; do the results reproduce? |

## `qont providers`

Pricing-catalog provenance.

| Command | What it does |
|---|---|
| `qont providers list` | Providers, device counts, verification date, and sources. |
| `qont providers verify` | Check that every catalog source URL is still reachable (network). |

## `qont plugin`

Discover and diagnose provider, backend, and SDK plugins. See
[Extending Qontinuum](plugins.md).

| Command | What it does |
|---|---|
| `qont plugin list` | Every discovered plugin: name, kind, source, availability. |
| `qont plugin show` | Full detail for one plugin (disambiguate with `--kind`). |
| `qont plugin doctor` | Plugin health: what loaded, what needs an extra, what's broken. |

## `qont registry`

Named circuit lineage (git for experiments).

| Command | What it does |
|---|---|
| `qont registry add` | Register a circuit (new version when the canonical hash changed). |
| `qont registry list` | Every registered circuit with its latest version. |
| `qont registry log` | Hash history, newest first. |
| `qont registry rm` | Remove a circuit and its whole lineage from the registry. |
| `qont registry show` | Latest version of one circuit. |
| `qont registry tag` | Tag a version (latest by default). |

## `qont report`

Render suite results (from --from suite.json, or by running the suite).

| Command | What it does |
|---|---|
| `qont report badge` | SVG status badge from the suite result. |
| `qont report engineering` | Full engineering report: recommendation, plan, provider & cost analysis, history. |
| `qont report html` | Self-contained HTML dashboard from run history (alias of qont dashboard). |
| `qont report json` | The raw versioned suite-result JSON. |
| `qont report junit` | JUnit XML — Jenkins/GitLab/Buildkite render quantum checks natively. |
| `qont report md` | Markdown report (same renderer as the PR comment, without cost table). |
| `qont report pr` | The full sticky PR comment (results + hardware cost table), rendered locally. |
| `qont report summary` | One-line machine-greppable summary (for shell pipelines). |

## `qont schedule`

Generate scheduled GitHub workflows (files only, never pushed).

| Command | What it does |
|---|---|
| `qont schedule nightly` | Emit a nightly (03:00 UTC) regression workflow. |
| `qont schedule weekly` | Emit a weekly (Monday 03:00 UTC) regression workflow. |

## `qont shots`

Statistical shot-count planning.

| Command | What it does |
|---|---|
| `qont shots floor` | Smallest TVD threshold that this shot count can statistically resolve. |
| `qont shots for-tvd` | Minimum shots so a perfect device reliably passes the given threshold. |
| `qont shots plan` | Audit every discovered test: are its shots sound for its thresholds? |
| `qont shots power` | Smallest distribution drift a two-sample snapshot test can detect. |

## `qont snapshot`

Manage golden-baseline snapshots.

| Command | What it does |
|---|---|
| `qont snapshot list` | List recorded golden baselines. |
| `qont snapshot prune` | Drop baselines whose tests no longer exist. |
| `qont snapshot rm` | Delete one baseline. |
| `qont snapshot show` | Full stored baseline for one test, including counts. |
| `qont snapshot update` | Re-record golden baselines for every snapshot-enabled test. |
| `qont snapshot verify` | Re-run snapshot tests and report drift without CI semantics. |

## `qont stats`

Statistics on counts JSON files (flat dicts, runner output, or {'counts': ...}).

| Command | What it does |
|---|---|
| `qont stats chi2` | Pearson goodness-of-fit test vs an expected distribution. |
| `qont stats compare` | Two-sample homogeneity test: were both files drawn from one distribution? |
| `qont stats describe` | Shots, support size, top outcomes, Shannon entropy. |
| `qont stats entropy` | Shannon entropy of the empirical distribution. |
| `qont stats fidelity` | Hellinger (classical) fidelity vs an expected distribution. |
| `qont stats tvd` | Total variation distance vs an expected distribution. |

## `qont telemetry`

Opt-in, anonymous community intelligence (off by default). See the
[Quantum Intelligence Network](intelligence-network.md) and [Privacy](privacy.md).

| Command | What it does |
|---|---|
| `qont telemetry status` | Show consent, endpoint, queued records, and community cache. |
| `qont telemetry enable` | Opt in to contributing anonymous execution metadata. |
| `qont telemetry disable` | Opt out; nothing further is captured or sent. |
| `qont telemetry preview` | Show exactly what would be contributed from your history. |
| `qont telemetry sync` | Flush queued records to the network (safe offline). |
| `qont telemetry community` | Show the locally cached community-intelligence snapshot. |
| `qont telemetry clear` | Delete all locally queued records without sending them. |

## `qont watch`

Re-run on change / poll live calibration.

| Command | What it does |
|---|---|
| `qont watch device` | Poll live calibration and alert on drift (needs a saved IBM account). |
| `qont watch test` | Re-run the suite whenever a q_test file changes (Ctrl-C to stop). |
