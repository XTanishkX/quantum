"""Render suite results + cost estimates as PR-comment markdown."""

from __future__ import annotations

from qontinuum.cost.estimator import CostEstimate
from qontinuum.report.schema import Status, SuiteResult

COMMENT_MARKER = "<!-- qontinuum-report -->"

_BADGE = {Status.PASS: "✅", Status.FAIL: "❌", Status.ERROR: "⚠️"}


def render_report(suite: SuiteResult, estimates: list[CostEstimate]) -> str:
    lines = [COMMENT_MARKER, "## ⚛️ Qontinuum report", ""]
    lines += _summary(suite)
    lines += _test_table(suite)
    lines += _failure_details(suite)
    lines += _cost_table(suite, estimates)
    lines += [
        "",
        f"<sub>qontinuum v{suite.tool_version} · cost figures are pre-run estimates "
        "from public pricing, not quotes</sub>",
    ]
    return "\n".join(lines) + "\n"


def _summary(suite: SuiteResult) -> list[str]:
    tally = suite.tally()
    total_shots = sum(t.shots for t in suite.tests)
    seed = f", seed {suite.seed}" if suite.seed is not None else ""
    return [
        f"{_BADGE[suite.status]} **{tally['pass']} passed · {tally['fail']} failed · "
        f"{tally['error']} errors** "
        f"({len(suite.tests)} tests, {total_shots:,} shots{seed})",
        "",
    ]


def _test_table(suite: SuiteResult) -> list[str]:
    if not suite.tests:
        return ["_No quantum tests found (files matching `q_test_*.py`)._", ""]
    lines = [
        "| Test | Backend | Shots | Checks | Status |",
        "|---|---|---:|---|:---:|",
    ]
    for t in suite.tests:
        checks = ", ".join(f"{_BADGE[c.status]} {c.name}" for c in t.checks) or "—"
        lines.append(
            f"| `{t.id}` | `{t.backend}` | {t.shots:,} | {checks} | {_BADGE[t.status]} |"
        )
    lines.append("")
    return lines


def _failure_details(suite: SuiteResult) -> list[str]:
    problems: list[str] = []
    for t in suite.tests:
        if t.error:
            problems.append(f"- ⚠️ `{t.id}`: {t.error}")
        for c in t.checks:
            if c.status is not Status.PASS and c.message:
                problems.append(f"- {_BADGE[c.status]} `{t.id}` **{c.name}**: {c.message}")
    if not problems:
        return []
    return ["**What went wrong**", "", *problems, ""]


def _cost_table(suite: SuiteResult, estimates: list[CostEstimate]) -> list[str]:
    if not estimates:
        return []
    lines = [
        "### 💸 Running this suite on real hardware",
        "",
        "| Provider | Device | Est. cost | Notes |",
        "|---|---|---:|---|",
    ]
    for est in estimates:
        if not est.feasible:
            price = "—"
        elif est.usd is not None:
            price = f"${est.usd:,.2f}"
        else:
            price = est.units
        lines.append(f"| {est.provider} | {est.display} | {price} | {est.note} |")
    lines.append("")
    return lines
