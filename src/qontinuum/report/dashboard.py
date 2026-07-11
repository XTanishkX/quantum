"""Render run history as a self-contained HTML dashboard.

No external assets, scripts, or CDNs — inline CSS and hand-rolled SVG, so the
file works offline, in CI artifact viewers, and behind firewalls.
"""

from __future__ import annotations

import html
from datetime import datetime

_STATUS_COLOR = {"pass": "#2da44e", "fail": "#cf222e", "error": "#bf8700"}

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
    tiles = [
        ("Runs recorded", str(len(records))),
        ("Pass rate", f"{passes / len(records):.0%}"),
        ("Last run", last["status"].upper()),
        ("Shots (last run)", f"{last.get('total_shots', 0):,}"),
    ]
    if last.get("cheapest_usd") is not None:
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
