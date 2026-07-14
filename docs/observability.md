# Observability & the execution history DB

Every `qont test`, `qont ci`, and `qont run` appends one JSON line to a local
execution database — `.qontinuum/history.jsonl` — and nothing leaves your
machine. That file is the substrate the dashboard renders, `qont history` mines,
the intelligence engine learns provider reliability from, and a future hosted
platform could ingest unchanged.

```
qont history list      # recent runs
qont history stats     # aggregate: pass rate, provider usage, hardware success
qont dashboard         # a self-contained HTML report of trends
```

## The record schema (versioned, forward-compatible)

Each line is a run record. The schema is **versioned** (`HISTORY_SCHEMA`) and
readers **migrate older lines up on read**, so a file written by any prior
version stays readable and new fields never break old consumers. Migration only
ever *adds* defaults — it never drops or reinterprets data.

Since schema 2, hardware runs carry a structured `execution` record:

| Field | Meaning |
|---|---|
| `mode` | `hardware` or `simulator` |
| `provider`, `target`, `backend` | where it ran |
| `estimated_cost_usd`, `actual_cost_usd` | pre-run estimate and (when known) the real charge |
| `queue_time_s`, `runtime_s` | timing |
| `routing_strategy` | which recommendation strategy chose this device, if any |
| `calibration_age_days`, `outcome`, `submitted_at`, `completed_at` | context |

Everything beyond `mode` is optional: a simulator run fills almost none of it, a
hardware run fills what it knows, and a scheduler or cloud layer can populate the
rest later **without a schema change**. That extensibility is the point — it is
the ingestion format a hosted "quantum intelligence network" would consume.

```python
from qontinuum.report.history import read_history, migrate_record
records = read_history(project_root)   # every line migrated to the current schema
```

## Analytics core

`qontinuum.intelligence.analytics` turns those records into engineering signals —
one core, many renderers (the `history stats` command, the dashboard, and
reports all call it):

- `summarize_executions` — runs, suite pass rate, hardware run count and success
  rate, provider usage, estimated spend
- `provider_usage` — executions per target
- `provider_comparison` — per-target runs, success rate, average duration
- `cost_series` / `fidelity_series` — time series for trend charts
- `routing_decisions` — the recorded "what ran where, and how it went" log

## The dashboard

`qont dashboard` writes a **single self-contained HTML file** — inline CSS and
hand-rolled SVG, no external assets, scripts, or CDNs — so it works offline, in
CI artifact viewers, and behind firewalls. It renders:

- headline tiles (runs, pass rate, hardware runs, hardware success rate, spend)
- a run-status timeline and check-statistic trends (drift detection)
- hardware **cost estimate over time**
- **provider usage** bars and a **provider comparison** table (success rate,
  average duration)
- a recent-runs table with commit shas

Hardware-specific sections appear only once you have hardware runs recorded;
a simulator-only project shows the core dashboard without them.
