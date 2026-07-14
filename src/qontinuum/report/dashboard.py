"""Render run history as a self-contained HTML dashboard.

No external assets, scripts, or CDNs — inline CSS and hand-rolled SVG, so the
file works offline, in CI artifact viewers, and behind firewalls.
"""

from __future__ import annotations

import html
from datetime import datetime

from qontinuum.intelligence import (
    cost_series,
    provider_comparison,
    provider_usage,
    summarize_executions,
)

_STATUS_COLOR = {"pass": "#2da44e", "fail": "#cf222e", "error": "#bf8700"}
_BAR_COLOR = "#0969da"

_CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 2rem auto;
       max-width: 960px; padding: 0 1rem; color: #1f2328; background: #ffffff; }
@media (prefers-color-scheme: dark) {
  body { color: #e6edf3; background: #0d1117; }
  .tile, table { border-color: #30363d !important; }
  th { background: #161b22 !important; }
}
h1 { font-size: 1.5rem; } h2 { font-size: 1.1rem; margin-top: 2rem; }
.tiles { display: flex; gap: 1rem; flex-wrap: wrap; }
.tile { border: 1px solid #d0d7de; border-radius: 8px; padding: .8rem 1.2rem; min-width: 8rem; }
.tile .value { font-size: 1.6rem; font-weight: 600; }
.tile .label { font-size: .8rem; opacity: .7; }
table { border-collapse: collapse; width: 100%; border: 1px solid #d0d7de; }
th, td { padding: .4rem .7rem; text-align: left; font-size: .85rem;
         border-bottom: 1px solid #d0d7de44; }
th { background: #f6f8fa; }
.badge { display: inline-block; border-radius: 999px; padding: .05rem .6rem;
         color: #fff; font-size: .75rem; }
.muted { opacity: .65; font-size: .85rem; }
svg text { fill: currentColor; }
"""


def render_dashboard(records: list[dict], *, title: str = "Qontinuum dashboard") -> str:
    body: list[str] = [f"<h1>⚛️ {html.escape(title)}</h1>"]
    if not records:
        body.append("<p class='muted'>No runs recorded yet — run <code>qont test</code>.</p>")
    else:
        body += _tiles(records)
        body += ["<h2>Run status timeline</h2>", _timeline_svg(records)]
        trend = _statistic_trends_svg(records)
        if trend:
            body += ["<h2>Check statistics over time</h2>", trend]
        cost = _cost_trend_svg(records)
        if cost:
            body += ["<h2>Hardware cost estimate over time</h2>", cost]
        usage = provider_usage(records)
        if usage:
            body += ["<h2>Provider usage</h2>", _bar_chart_svg(usage, unit=" runs")]
        comparison = provider_comparison(records)
        if comparison:
            body += ["<h2>Provider comparison</h2>", _provider_table(comparison)]
        body += ["<h2>Recent runs</h2>", _runs_table(records)]
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    body.append(
        f"<p class='muted'>Generated {html.escape(generated)} by qontinuum · "
        "self-contained file, no external assets</p>"
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f"<body>{''.join(body)}</body></html>"
    )


def _tiles(records: list[dict]) -> list[str]:
    last = records[-1]
    passes = sum(1 for r in records if r["status"] == "pass")
    analytics = summarize_executions(records)
    tiles = [
        ("Runs recorded", str(len(records))),
        ("Pass rate", f"{passes / len(records):.0%}"),
        ("Last run", last["status"].upper()),
        ("Shots (last run)", f"{last.get('total_shots', 0):,}"),
    ]
    if analytics.get("hardware_runs"):
        tiles.append(("Hardware runs", str(analytics["hardware_runs"])))
        if analytics.get("hardware_success_rate"):
            tiles.append(("HW success rate", analytics["hardware_success_rate"]))
    if analytics.get("estimated_spend_usd") is not None:
        tiles.append(("Est. HW spend (total)", f"${analytics['estimated_spend_usd']:,.2f}"))
    elif last.get("cheapest_usd") is not None:
        tiles.append(("Cheapest HW cost (last run)", f"${last['cheapest_usd']:,.2f}"))
    out = ["<div class='tiles'>"]
    for label, value in tiles:
        color = _STATUS_COLOR.get(value.lower(), "inherit")
        style = f" style='color:{color}'" if value.lower() in _STATUS_COLOR else ""
        out.append(
            f"<div class='tile'><div class='value'{style}>{html.escape(value)}</div>"
            f"<div class='label'>{html.escape(label)}</div></div>"
        )
    out.append("</div>")
    return out


def _timeline_svg(records: list[dict], *, max_runs: int = 60) -> str:
    recent = records[-max_runs:]
    cell, gap, h = 14, 3, 26
    width = len(recent) * (cell + gap)
    cells = []
    for i, r in enumerate(recent):
        color = _STATUS_COLOR[r["status"]]
        label = f"{r['created_at']} — {r['status']}"
        cells.append(
            f"<rect x='{i * (cell + gap)}' y='4' width='{cell}' height='{cell}' rx='3'"
            f" fill='{color}'><title>{html.escape(label)}</title></rect>"
        )
    return (
        f"<svg viewBox='0 0 {max(width, 1)} {h}' width='{max(width, 1)}' height='{h}'"
        f" role='img' aria-label='status timeline'>{''.join(cells)}</svg>"
    )


def _statistic_trends_svg(records: list[dict], *, w: int = 900, h: int = 220) -> str:
    """Polyline per (test, check) for checks that report a statistic (e.g. TVD)."""
    series: dict[str, list[tuple[int, float, float | None]]] = {}
    for run_idx, r in enumerate(records):
        for t in r.get("tests", []):
            for c in t.get("checks", []):
                if c.get("statistic") is None:
                    continue
                key = f"{t['id']} · {c['name']}"
                series.setdefault(key, []).append(
                    (run_idx, c["statistic"], c.get("threshold"))
                )
    series = {k: v for k, v in series.items() if len(v) >= 2}
    if not series:
        return ""

    pad, plot_w, plot_h = 40, w - 60, h - 60
    max_y = max(max(v for _, v, _ in pts) for pts in series.values())
    thresholds = [th for pts in series.values() for _, _, th in pts if th is not None]
    if thresholds:
        max_y = max(max_y, max(thresholds))
    max_y = max(max_y * 1.15, 1e-6)
    max_x = max(1, len(records) - 1)

    def sx(run_idx: int) -> float:
        return pad + run_idx / max_x * plot_w

    def sy(value: float) -> float:
        return pad + (1 - value / max_y) * plot_h

    palette = ["#0969da", "#8250df", "#bf3989", "#1a7f37", "#9a6700", "#cf222e"]
    parts = [
        f"<line x1='{pad}' y1='{pad + plot_h}' x2='{pad + plot_w}' y2='{pad + plot_h}'"
        " stroke='#8886' />",
        f"<text x='{pad - 6}' y='{pad + 4}' text-anchor='end' font-size='11'>"
        f"{max_y:.3g}</text>",
        f"<text x='{pad - 6}' y='{pad + plot_h + 4}' text-anchor='end' font-size='11'>0</text>",
    ]
    legend_y = 14
    for i, (key, pts) in enumerate(sorted(series.items())):
        color = palette[i % len(palette)]
        path = " ".join(f"{sx(x):.1f},{sy(v):.1f}" for x, v, _ in pts)
        parts.append(
            f"<polyline points='{path}' fill='none' stroke='{color}' stroke-width='2'/>"
        )
        threshold = next((th for _, _, th in reversed(pts) if th is not None), None)
        if threshold is not None:
            y = sy(threshold)
            parts.append(
                f"<line x1='{pad}' y1='{y:.1f}' x2='{pad + plot_w}' y2='{y:.1f}'"
                f" stroke='{color}' stroke-dasharray='4 4' opacity='.5'/>"
            )
        parts.append(
            f"<circle cx='{pad + plot_w + 8}' cy='{legend_y}' r='4' fill='{color}'/>"
            f"<text x='{pad + plot_w + 16}' y='{legend_y + 4}' font-size='11'>"
            f"{html.escape(key)}</text>"
        )
        legend_y += 16
    return (
        f"<svg viewBox='0 0 {w + 320} {h}' width='100%' role='img'"
        f" aria-label='check statistic trends'>{''.join(parts)}</svg>"
        "<p class='muted'>Dashed lines are the corresponding assertion thresholds.</p>"
    )


def _cost_trend_svg(records: list[dict], *, w: int = 900, h: int = 180) -> str:
    """Line chart of the cheapest hardware estimate per run over time."""
    series = cost_series(records)
    if len(series) < 2:
        return ""
    values = [p["usd"] for p in series]
    pad, plot_w, plot_h = 44, w - 64, h - 56
    max_y = max(max(values) * 1.15, 1e-6)
    max_x = max(1, len(series) - 1)

    def sx(i: int) -> float:
        return pad + i / max_x * plot_w

    def sy(v: float) -> float:
        return pad + (1 - v / max_y) * plot_h

    points = " ".join(f"{sx(i):.1f},{sy(v):.1f}" for i, v in enumerate(values))
    area = f"{pad},{pad + plot_h} {points} {pad + plot_w},{pad + plot_h}"
    parts = [
        f"<polygon points='{area}' fill='{_BAR_COLOR}22'/>",
        f"<polyline points='{points}' fill='none' stroke='{_BAR_COLOR}' stroke-width='2'/>",
        f"<line x1='{pad}' y1='{pad + plot_h}' x2='{pad + plot_w}' y2='{pad + plot_h}'"
        " stroke='#8886'/>",
        f"<text x='{pad - 6}' y='{pad + 4}' text-anchor='end' font-size='11'>"
        f"${max_y:,.2f}</text>",
        f"<text x='{pad - 6}' y='{pad + plot_h + 4}' text-anchor='end' font-size='11'>$0</text>",
    ]
    return (
        f"<svg viewBox='0 0 {w} {h}' width='100%' role='img'"
        f" aria-label='hardware cost estimate over time'>{''.join(parts)}</svg>"
    )


def _bar_chart_svg(counts: dict[str, int], *, unit: str = "", w: int = 900) -> str:
    """Horizontal bars for a name→count mapping (e.g. provider usage)."""
    if not counts:
        return ""
    items = list(counts.items())
    row_h, label_w = 24, 220
    bar_max = w - label_w - 90
    top = max(counts.values()) or 1
    rows = []
    for i, (name, count) in enumerate(items):
        y = i * row_h + 4
        bar = max(2, count / top * bar_max)
        rows.append(
            f"<text x='0' y='{y + 14}' font-size='12'>{html.escape(name)}</text>"
            f"<rect x='{label_w}' y='{y + 3}' width='{bar:.1f}' height='14' rx='3'"
            f" fill='{_BAR_COLOR}'/>"
            f"<text x='{label_w + bar + 6:.1f}' y='{y + 14}' font-size='11'>"
            f"{count}{html.escape(unit)}</text>"
        )
    height = len(items) * row_h + 8
    return (
        f"<svg viewBox='0 0 {w} {height}' width='100%' role='img'"
        f" aria-label='provider usage'>{''.join(rows)}</svg>"
    )


def _provider_table(rows: list[dict]) -> str:
    body = []
    for r in rows:
        rate = f"{r['success_rate']:.0%}"
        color = _STATUS_COLOR["pass"] if r["success_rate"] >= 0.9 else _STATUS_COLOR["error"]
        dur = f"{r['avg_duration_ms']:,.0f} ms" if r.get("avg_duration_ms") is not None else "—"
        body.append(
            f"<tr><td><code>{html.escape(str(r['target']))}</code></td>"
            f"<td>{r['runs']}</td>"
            f"<td style='color:{color}'>{rate}</td><td>{dur}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Target</th><th>Runs</th><th>Success rate</th>"
        f"<th>Avg duration</th></tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _runs_table(records: list[dict], *, max_rows: int = 20) -> str:
    rows = []
    for r in reversed(records[-max_rows:]):
        badge = (
            f"<span class='badge' style='background:{_STATUS_COLOR[r['status']]}'>"
            f"{r['status']}</span>"
        )
        tally = r.get("tally", {})
        cost = f"${r['cheapest_usd']:,.2f}" if r.get("cheapest_usd") is not None else "—"
        sha = r.get("git_sha") or "—"
        rows.append(
            f"<tr><td>{html.escape(r['created_at'])}</td><td>{badge}</td>"
            f"<td>{tally.get('pass', 0)}✓ {tally.get('fail', 0)}✗ {tally.get('error', 0)}!</td>"
            f"<td>{r.get('total_shots', 0):,}</td><td>{cost}</td>"
            f"<td><code>{html.escape(sha)}</code></td>"
            f"<td>{'' if r.get('seed') is None else r['seed']}</td></tr>"
        )
    return (
        "<table><thead><tr><th>When</th><th>Status</th><th>Tests</th><th>Shots</th>"
        "<th>Cheapest HW</th><th>Commit</th><th>Seed</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
