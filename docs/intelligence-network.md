# The Quantum Intelligence Network

Hardware reliability, queue behaviour, and real costs are things every quantum
team rediscovers alone. The Quantum Intelligence Network is an **optional**,
privacy-preserving way to pool *anonymous engineering metadata* so that
Qontinuum's recommendations get better for everyone — without anyone sharing
circuits, results, or identity.

It is **off by default**. Qontinuum is fully functional offline forever; the
network only ever *adds* signal when you opt in.

## Design at a glance

```
  qont run (hardware)
        │  (only if you opted in)
        ▼
  scrub ──► allowlist-only TelemetryRecord ──► local outbox (.qontinuum/telemetry)
        │                                            │
        │                                            │  qont telemetry sync
        ▼                                            ▼
  nothing else leaves the machine            HTTPS endpoint  ──►  aggregation
                                                     │
                                     community.json  ◄── CommunityAggregate
                                                     │
                                                     ▼
                             assess_health() blends a "community" signal
                             into per-device reliability (attributed)
```

Every arrow is opt-in and offline-tolerant. If you never enable telemetry,
never set an endpoint, or are simply offline, records queue locally (or aren't
built at all) and every command behaves exactly as before.

## What is shared — and what never is

The wire format is a strict **allowlist**
([`TelemetryRecord`](https://github.com/XTanishkX/quantum/blob/main/src/qontinuum/telemetry/schema.py)):
a record can only contain the fields declared on that model, so nothing else can
leak even as history schemas evolve.

**Shared** (anonymous engineering metadata): public provider & device ids,
outcome (pass/fail), runtime, queue time, estimated cost, a *bucketed* shot
count, calibration age, routing strategy, tool version, the calendar day, and a
random `install_id` that maps to nothing.

**Never shared:** circuits, gates, or QASM · measurement counts or probability
distributions · snapshots, test ids, file paths, git shas, or seeds ·
credentials, API keys, or any personal information.

See [Privacy](privacy.md) for the full contract, and run `qont telemetry
preview` to see the *literal* records that would be sent from your history.

## Architecture properties

- **Consent-gated.** `telemetry.enabled` defaults to `false`; capture, queue,
  and sync are all no-ops until you `qont telemetry enable`.
- **Local caching / outbox.** Records are captured to an append-only
  `.qontinuum/telemetry/outbox.jsonl` and only leave on an explicit sync.
- **Integrity.** Each record is signed with a sha256 over its canonical form;
  tampered or corrupt lines are dropped on read, never trusted.
- **Schema versioning.** Both the upload record and the community snapshot carry
  a `schema_version`; incompatible snapshots are ignored rather than misread.
- **Secure transport.** Sync refuses any non-`https://` endpoint. The network
  call is a single injected seam (`transport`), so it is auditable and testable.
- **Graceful offline.** No endpoint, no network, a timeout, a non-2xx, or a bad
  response all leave the queue intact and report why — telemetry never blocks or
  breaks a run.

## How it improves recommendations

When a community snapshot has been synced, `assess_health` blends a per-device
`community` success signal into reliability, weighted by sample size and clearly
attributed as a `community` data source (visible in `qont health`). Confidence
rises with the evidence. With no snapshot present, the assessment is identical to
the offline catalog + local-history result — community intelligence is always
additive, never load-bearing.

## Commands

```console
$ qont telemetry status      # consent, endpoint, queued records, community cache
$ qont telemetry enable      # opt in (states exactly what is shared)
$ qont telemetry preview     # the literal records that would be sent
$ qont telemetry sync        # flush the outbox (safe offline)
$ qont telemetry community   # the cached community snapshot
$ qont telemetry disable     # opt out
$ qont telemetry clear       # delete queued records without sending
```

## Running your own endpoint

The client speaks a tiny HTTP contract so the network is not tied to any single
host: `POST {endpoint}/contribute` with `{schema, install_id, records[]}`, and
`GET/POST {endpoint}/community` returning `{"community": <CommunityAggregate>}`.
Set it with `qont config set telemetry.endpoint https://…`. No hosted endpoint
is required to use Qontinuum; the aggregation service is deliberately out of the
client's trust boundary.
