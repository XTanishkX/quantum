# Security Policy

## Supported versions

The latest minor release receives fixes. Pre-1.0, please stay current.

## What Qontinuum touches

- **Credentials**: Qontinuum never stores provider credentials itself. IBM
  access uses `qiskit-ibm-runtime`'s saved-account mechanism; AWS uses your
  ambient AWS credentials. Nothing is written to Qontinuum files.
- **Network**: everything is offline by default. Only `@live` backends,
  `qont device queue/drift`, `qont watch device`, `qont providers verify`,
  and `qont run` reach the network — each says so in its help text.
- **Spending**: hardware submission is guarded twice (`--max-cost` per
  invocation, `qont budget` caps per project). Estimates are computed before
  anything is submitted.

## Reporting a vulnerability

Please open a private report via GitHub Security Advisories
(Security tab → "Report a vulnerability") on
[XTanishkX/quantum](https://github.com/XTanishkX/quantum). Do not open public
issues for exploitable problems. Expect an acknowledgment within a week.
