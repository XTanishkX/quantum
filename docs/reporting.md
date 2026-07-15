# Reporting

Qontinuum renders results for wherever your pipeline needs them — from a
one-line shell summary to a full engineering report. All formats come from the
`qont report` group and share the same versioned suite-result JSON as their
source of truth.

## Formats

| Command | Output | Use |
|---|---|---|
| `qont report junit` | JUnit XML | Jenkins/GitLab/Buildkite render quantum checks natively |
| `qont report badge` | SVG badge | README / dashboards |
| `qont report md` | Markdown | docs, wikis, PR bodies |
| `qont report pr` | Markdown + cost table | the sticky PR comment, rendered locally |
| `qont report json` | Versioned suite JSON | machine consumption, archival |
| `qont report html` | Self-contained HTML dashboard | trends & observability |
| `qont report summary` | One greppable line | shell pipelines |
| `qont report engineering` | Full engineering report | the "where should this run, and why?" decision doc |

Every format can read a prior run (`--from suite.json`) or run the suite fresh,
and write to a file (`--out`) or stdout.

## The engineering report

`qont report engineering` is the platform's decision document. It pulls the whole
intelligence layer into one markdown file:

- **Execution plan** — the selected device with expected runtime, queue, cost,
  and fidelity, plus its **risk level** and **confidence**, the reasons it was
  chosen, risks, fallbacks, assumptions, and missing evidence.
- **Ranked recommendations** — the feasible devices under your chosen strategy.
- **Provider analysis** — per-device reliability from calibration, local
  history, and (if synced) community intelligence, with the evidence behind each.
- **Cost analysis** — estimated hardware cost per device.
- **Historical context** — pass rate, hardware success rate, and spend from your
  local run history.

```console
$ qont report engineering --path . --strategy balanced --out report.md
$ qont report engineering --strategy value --budget 20
```

It reuses the exact engine behind `qont recommend`, `qont plan`, and `qont
health`, so the report never disagrees with the individual commands. The renderer
is pure (structured objects in, markdown out), so it is easy to test and to embed
in CI.

## Confidence and honesty

Reports never present a number without context. Fidelity is labelled as a
per-shot survival estimate (not a measured value); queue time is blank when it is
not modelled offline; and every plan carries a confidence score reflecting how
much evidence backed it. Missing evidence is stated, not hidden.
