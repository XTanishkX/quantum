# Security & secure defaults

Qontinuum is local-first and designed to be safe to run on untrusted inputs and
in CI. This page documents the security posture; to **report** a vulnerability
see [SECURITY.md](https://github.com/XTanishkX/quantum/blob/main/SECURITY.md).

## Secure defaults

- **Telemetry is off.** No network activity happens unless you opt in
  ([Privacy](privacy.md)). The default install talks to nothing.
- **HTTPS-only egress.** The two network paths — telemetry sync and catalog
  source verification — refuse non-`https://` URLs and use bounded timeouts.
- **Spend guard defaults to $0.** Hardware runs submit nothing until you
  explicitly authorize a budget.
- **Config is a whitelist.** Unknown keys are rejected loudly; values are parsed
  with `tomllib` / JSON, never evaluated.

## Input validation

- **No dynamic code execution.** The codebase contains no `eval`, `exec`,
  `pickle`, `os.system`, `shell=True`, or unsafe YAML; catalogs load via
  `yaml.safe_load`.
- **Everything crossing a trust boundary is schema-validated.** History records,
  telemetry records, community snapshots, and suite results are parsed through
  typed Pydantic models; malformed or incompatible data is rejected or dropped,
  never trusted. Downloaded community snapshots are validated *before* they can
  influence a recommendation.
- **QASM/SDK inputs** are parsed by the underlying SDKs; Qontinuum treats circuit
  sources as data and never executes file contents.

## Telemetry & network

- **Allowlist payloads.** Telemetry can only contain the fields declared on
  `TelemetryRecord`; there is no field for circuits, distributions, counts,
  source, credentials, or identity, so they cannot be transmitted.
- **Integrity.** Queued records are sha256-signed and re-verified on read;
  tampered lines are discarded.
- **Single auditable seam.** All outbound HTTP goes through one injected
  `transport` function, so the network surface is small and reviewable. Any
  failure is contained — telemetry never affects a run's outcome.
- **No credentials handled.** Qontinuum stores and transmits no API keys or
  tokens; provider auth is delegated entirely to the vendor SDKs and their own
  credential stores.

## Plugin isolation

Third-party plugins are discovered via entry points and loaded defensively: a
plugin that fails to import (or raises during discovery) is recorded as
unavailable with its error and **never crashes** the CLI. A plugin runs with the
same privileges as the host process — install only plugins you trust, exactly as
with any Python package. `qont plugin doctor` surfaces load failures and missing
dependencies.

## Reproducibility & supply chain

- Releases are built and published to PyPI via GitHub Actions **trusted
  publishing** (OIDC, no long-lived tokens).
- The pricing catalog records source URLs and a verification date; `qont
  providers verify` checks source reachability.
- Reproducibility bundles (`qont pack`) capture the environment lock alongside
  seeded results for auditable re-runs.
