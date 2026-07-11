import json
import textwrap

from typer.testing import CliRunner

from qontinuum.cli import app
from qontinuum.report.dashboard import render_dashboard
from qontinuum.report.history import append_history, history_path, read_history
from qontinuum.report.schema import CheckResult, Status, SuiteResult
from qontinuum.report.schema import TestResult as TestResultModel

PASSING = """
from qiskit import QuantumCircuit
from qontinuum import qtest, assert_distribution

@qtest(shots=1000)
def bell():
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc

@bell.check
def entangled(result):
    assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.08)
"""


def make_suite(statistic=0.02) -> SuiteResult:
    return SuiteResult(
        tool_version="0.1.0",
        seed=1,
        tests=[
            TestResultModel(
                id="q_test_x.py::bell",
                status=Status.PASS,
                backend="aer",
                shots=1000,
                circuit_hash="sha256:ab",
                checks=[
                    CheckResult(
                        name="entangled",
                        status=Status.PASS,
                        statistic=statistic,
                        threshold=0.08,
                    )
                ],
            )
        ],
    )


class TestHistory:
    def test_append_and_read_roundtrip(self, tmp_path):
        append_history(tmp_path, make_suite(), cheapest_usd=1.23)
        append_history(tmp_path, make_suite(0.03))
        records = read_history(tmp_path)
        assert len(records) == 2
        assert records[0]["cheapest_usd"] == 1.23
        assert records[1]["cheapest_usd"] is None
        assert records[0]["tests"][0]["checks"][0]["statistic"] == 0.02

    def test_history_excludes_counts(self, tmp_path):
        append_history(tmp_path, make_suite())
        raw = history_path(tmp_path).read_text()
        assert "counts" not in raw

    def test_cli_test_appends_history_by_default(self, tmp_path):
        (tmp_path / "q_test_a.py").write_text(textwrap.dedent(PASSING))
        result = CliRunner().invoke(app, ["test", str(tmp_path), "--seed", "5"])
        assert result.exit_code == 0
        assert len(read_history(tmp_path)) == 1

    def test_cli_no_history_flag(self, tmp_path):
        (tmp_path / "q_test_a.py").write_text(textwrap.dedent(PASSING))
        CliRunner().invoke(app, ["test", str(tmp_path), "--no-history"])
        assert read_history(tmp_path) == []

    def test_ci_records_cheapest_cost(self, tmp_path):
        (tmp_path / "q_test_a.py").write_text(textwrap.dedent(PASSING))
        md = tmp_path / "r.md"
        CliRunner().invoke(app, ["ci", str(tmp_path), "--md", str(md)])
        (record,) = read_history(tmp_path)
        # Rigetti at 1000 shots: 0.30 + 1000*0.000425 = 0.725
        assert record["cheapest_usd"] == 0.725


class TestDashboard:
    def render(self, tmp_path, n_runs=3):
        for i in range(n_runs):
            append_history(tmp_path, make_suite(0.01 * (i + 1)), cheapest_usd=1.0)
        return render_dashboard(read_history(tmp_path))

    def test_self_contained_html(self, tmp_path):
        html_text = self.render(tmp_path)
        assert html_text.startswith("<!DOCTYPE html>")
        for banned in ("http://", "https://", "<script"):
            assert banned not in html_text

    def test_shows_tiles_and_trend(self, tmp_path):
        html_text = self.render(tmp_path)
        assert "Pass rate" in html_text
        assert "polyline" in html_text  # statistic trend chart
        assert "stroke-dasharray" in html_text  # threshold line

    def test_empty_history_renders_hint(self):
        assert "No runs recorded" in render_dashboard([])

    def test_cli_dashboard_writes_file(self, tmp_path):
        (tmp_path / "q_test_a.py").write_text(textwrap.dedent(PASSING))
        CliRunner().invoke(app, ["test", str(tmp_path)])
        out = tmp_path / "dash.html"
        result = CliRunner().invoke(app, ["dashboard", str(tmp_path), "--out", str(out)])
        assert result.exit_code == 0, result.output
        assert out.read_text().startswith("<!DOCTYPE html>")

    def test_cli_dashboard_without_history_exits_2(self, tmp_path):
        result = CliRunner().invoke(app, ["dashboard", str(tmp_path)])
        assert result.exit_code == 2

    def test_malformed_lines_are_not_silently_lost(self, tmp_path):
        append_history(tmp_path, make_suite())
        path = history_path(tmp_path)
        path.write_text(path.read_text() + "\n \n")  # trailing blank lines ok
        assert len(read_history(tmp_path)) == 1


def test_history_record_is_json_lines(tmp_path):
    append_history(tmp_path, make_suite())
    append_history(tmp_path, make_suite())
    lines = history_path(tmp_path).read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)
