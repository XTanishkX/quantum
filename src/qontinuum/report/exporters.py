"""JUnit XML and SVG badge exporters — speak the formats CI systems already eat."""

from __future__ import annotations

from xml.sax.saxutils import escape as xml_escape

from qontinuum.report.schema import Status, SuiteResult


def render_junit(suite: SuiteResult, *, suite_name: str = "qontinuum") -> str:
    """JUnit XML: one <testcase> per check so CI UIs show quantum checks natively."""
    cases: list[str] = []
    tests = failures = errors = 0
    total_time = 0.0
    for test in suite.tests:
        time_s = (test.duration_ms or 0) / 1000
        total_time += time_s
        checks = test.checks or []
        if not checks:
            tests += 1
            body = ""
            if test.status is Status.ERROR:
                errors += 1
                body = f'<error message="{xml_escape(test.error)}"/>'
            cases.append(
                f'<testcase classname="{xml_escape(test.id)}" name="run" '
                f'time="{time_s:.3f}">{body}</testcase>'
            )
            continue
        per_check = time_s / len(checks)
        for check in checks:
            tests += 1
            body = ""
            if check.status is Status.FAIL:
                failures += 1
                body = f'<failure message="{xml_escape(check.message)}"/>'
            elif check.status is Status.ERROR:
                errors += 1
                body = f'<error message="{xml_escape(check.message)}"/>'
            cases.append(
                f'<testcase classname="{xml_escape(test.id)}" '
                f'name="{xml_escape(check.name)}" time="{per_check:.3f}">{body}</testcase>'
            )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<testsuite name="{xml_escape(suite_name)}" tests="{tests}" '
        f'failures="{failures}" errors="{errors}" time="{total_time:.3f}">\n  '
        + "\n  ".join(cases)
        + "\n</testsuite>\n"
    )


_BADGE_COLORS = {"pass": "#2da44e", "fail": "#cf222e", "error": "#bf8700"}


def render_badge(status: str, *, label: str = "quantum tests") -> str:
    """Shields-style SVG badge for READMEs and dashboards."""
    value = {"pass": "passing", "fail": "failing", "error": "error"}.get(status, status)
    color = _BADGE_COLORS.get(status, "#8b94a7")
    label_w = 6 * len(label) + 22
    value_w = 6 * len(value) + 22
    total = label_w + value_w
    grad = ('<linearGradient id="s" x2="0" y2="100%">'
            '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
            '<stop offset="1" stop-opacity=".1"/></linearGradient>')
    font = "Verdana,Geneva,DejaVu Sans,sans-serif"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" '
        f'aria-label="{label}: {value}">\n'
        f"  {grad}\n"
        f'  <clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>\n'
        f'  <g clip-path="url(#r)">\n'
        f'    <rect width="{label_w}" height="20" fill="#555"/>\n'
        f'    <rect x="{label_w}" width="{value_w}" height="20" fill="{color}"/>\n'
        f'    <rect width="{total}" height="20" fill="url(#s)"/>\n'
        f"  </g>\n"
        f'  <g fill="#fff" text-anchor="middle" font-family="{font}" font-size="11">\n'
        f'    <text x="{label_w / 2}" y="14">{label}</text>\n'
        f'    <text x="{label_w + value_w / 2}" y="14">{value}</text>\n'
        f"  </g>\n</svg>\n"
    )
