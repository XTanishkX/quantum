# Privacy

Qontinuum is **local-first and private by default**. It runs entirely on your
machine, needs no account, and sends nothing anywhere unless you explicitly opt
in to the [Quantum Intelligence Network](intelligence-network.md). This page is
the plain-English contract for that one optional feature.

## Default: nothing leaves your machine

Out of the box, telemetry is **off** (`telemetry.enabled = false`). No records
are built, queued, or transmitted. Every command — testing, cost, routing,
recommendations, dashboards — works fully offline, forever. You can verify the
state anytime:

```console
$ qont telemetry status
```

## If you opt in

`qont telemetry enable` opts this project in and generates a random, anonymous
`install_id` (a UUID that maps to no personal data). From then on, **hardware
runs** (`qont run`) append one anonymous record to a local outbox. Records leave
your machine only when you run `qont telemetry sync`, and only to an endpoint you
have configured over HTTPS.

### Exactly what is shared

Only this anonymous engineering metadata, per hardware execution:

- public provider and device identifiers (from the pricing catalog)
- outcome (pass / fail), runtime, queue time, estimated cost
- a **bucketed** shot count (e.g. `1001-4000`, never the exact number)
- calibration age, routing strategy
- tool version, the calendar **day** (never the time of day)
- the random `install_id`

### What is never shared

- circuits, gates, or QASM
- measurement counts or probability distributions
- snapshots, test ids, file paths, git shas, or seeds
- credentials, API keys, or any personal information

These are not "filtered out" — the upload format has **no field for them**, and
the scrubber builds records by copying a fixed allowlist, so a future change to
internal data structures cannot start leaking them. See it for yourself:

```console
$ qont telemetry preview     # the complete, literal payload from your history
```

## Your controls

| Action | Command |
|---|---|
| Check status | `qont telemetry status` |
| Opt in | `qont telemetry enable` |
| See what would be sent | `qont telemetry preview` |
| Opt out | `qont telemetry disable` |
| Delete queued records (no send) | `qont telemetry clear` |

Disabling stops all capture and transmission immediately. Clearing deletes the
local outbox without sending it.

## Anonymity & security notes

- The `install_id` is random and unlinkable; day-granularity timestamps and
  bucketed sizes further limit fingerprinting.
- Uploads are refused over anything but `https://`.
- Downloaded community snapshots are schema-validated before use, so a bad or
  incompatible response can never poison your recommendations.
- Nothing about telemetry can change a run's result: capture and sync are
  wrapped so any failure is silent to your workflow.

If you operate your own aggregation endpoint, you are responsible for its
handling of the data it receives; the client's job is to ensure only the
allowlisted, anonymous metadata above ever leaves the machine.
