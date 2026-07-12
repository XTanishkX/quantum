# Qontinuum

**The quantum DevOps toolchain** — pytest + Infracost + Datadog + git plumbing,
built quantum-native. 110 commands, offline-first, Apache-2.0.

```sh
pip install qontinuum
qont init
qont test
```

## Why this exists

Quantum programs return probability distributions sampled from noisy, drifting
hardware whose prices differ 100× between vendors for the same job. Nothing in
the classical delivery pipeline understands any of that. Qontinuum does:

| DevOps concept | Classical tool | Qontinuum |
|---|---|---|
| Test runner | pytest | `qont test` — statistical assertions with soundness floors |
| Linting | ruff | `qont lint` — Q-rules for quantum-test footguns |
| Cost on PRs | Infracost | `qont cost` + the GitHub Action's sticky comment |
| Build cache | Bazel/Turborepo | `qont cache` — content-addressed simulation results |
| Load testing | k6/Locust | `qont noise headroom` — how much drift survives? |
| Bisecting | git bisect | `qont history bisect` — which run broke the physics? |
| FinOps | cloud budgets | `qont budget` — caps enforced before submission |
| Provenance | SBOM/attestations | `qont pack` — re-runnable reproducibility bundles |
| Flake detection | CI retries | `qont fuzz` — empirical pass rates, Wilson CIs |
| Monitoring | Datadog | `qont dashboard` + `qont watch device` |

Start with [Getting started](getting-started.md), or jump to the full
[command reference](commands.md).

- **Website**: <https://xtanishkx.github.io/quantum/>
- **PyPI**: <https://pypi.org/project/qontinuum/>
- **Source**: <https://github.com/XTanishkX/quantum>
