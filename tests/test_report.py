import textwrap

from typer.testing import CliRunner

from qontinuum.cli import app
from qontinuum.cost import estimate_circuit
from qontinuum.report.markdown import COMMENT_MARKER, render_report
from qontinuum.report.schema import CheckResult, Status, SuiteResult
from qontinuum.report.schema import TestResult as TestResultModel


def make_suite(status=Status.PASS, message="") -> SuiteResult:
    check = CheckResult(name="is_entangled", status=status, message=message)
    test = TestResultModel(
        id="q_test_bell.py::bell_pair",
        status=status,
        backend="aer",
        shots=4000,
        circuit_hash="sha256:abc",
        checks=[check],
    )
    return SuiteResult(tool_version="0.1.0", seed=42, tests=[test])


def bell_estimates():
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return estimate_circuit(qc, shots=4000)


class TestRenderReport:
    def test_contains_sticky_marker_and_summary(self):
        md = render_report(make_suite(), bell_estimates())
        assert md.startswith(COMMENT_MARKER)
        assert "1 passed · 0 failed · 0 errors" in md
        assert "4,000 shots" in md

    def test_pass_report_has_no_failure_section(self):
        md = render_report(make_suite(), bell_estimates())
        assert "What went wrong" not in md

    def test_failure_message_surfaces(self):
        md = render_report(
            make_suite(Status.FAIL, "TVD 0.5 exceeds threshold 0.05"), bell_estimates()
        )
        assert "What went wrong" in md
        assert "TVD 0.5 exceeds threshold 0.05" in md

    def test_cost_table_lists_dollar_and_credit_prices(self):
        md = render_report(make_suite(), bell_estimates())
        assert "$2.00" in md  # Rigetti at 4000 shots
        assert "HQC" in md
        assert "not quotes" in md

    def test_empty_suite_renders_gracefully(self):
        md = render_report(SuiteResult(tool_version="0.1.0"), [])
        assert "No quantum tests found" in md


class TestCiCommand:
    def test_ci_writes_report_and_exits_zero_on_pass(self, tmp_path):
        (tmp_path / "q_test_ok.py").write_text(
            textwrap.dedent(
                """
                from qiskit import QuantumCircuit
                from qontinuum import qtest, assert_distribution

                @qtest(shots=2000)
                def bell():
                    qc = QuantumCircuit(2)
                    qc.h(0)
                    qc.cx(0, 1)
                    qc.measure_all()
                    return qc

                @bell.check
                def looks_entangled(result):
                    assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.06)
                """
            )
        )
        md = tmp_path / "report.md"
        result = CliRunner().invoke(
            app, ["ci", str(tmp_path), "--md", str(md), "--seed", "9"]
        )
        assert result.exit_code == 0, result.output
        content = md.read_text()
        assert COMMENT_MARKER in content
        assert "Running this suite on real hardware" in content

    def test_ci_exit_code_one_on_failure(self, tmp_path):
        (tmp_path / "q_test_bad.py").write_text(
            textwrap.dedent(
                """
                from qiskit import QuantumCircuit
                from qontinuum import qtest, assert_probability

                @qtest(shots=1000)
                def coin():
                    qc = QuantumCircuit(1)
                    qc.h(0)
                    qc.measure_all()
                    return qc

                @coin.check
                def always_zero(result):
                    assert_probability(result, "0", min_p=0.99)
                """
            )
        )
        md = tmp_path / "report.md"
        result = CliRunner().invoke(app, ["ci", str(tmp_path), "--md", str(md)])
        assert result.exit_code == 1
        assert "What went wrong" in md.read_text()
