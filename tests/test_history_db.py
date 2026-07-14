"""History DB v2: versioned schema, migration, and the v2 dashboard sections."""

from __future__ import annotations

import json

from qontinuum.report.dashboard import render_dashboard
from qontinuum.report.history import (
    HISTORY_SCHEMA,
    ExecutionRecord,
    append_history,
    history_path,
    migrate_record,
    read_history,
)
from qontinuum.report.schema import Status, SuiteResult
from qontinuum.report.schema import TestResult as _TestResult


def _suite(status=Status.PASS, backend="aer") -> SuiteResult:
    return SuiteResult(
        tool_version="0.4.0",
        tests=[_TestResult(id="t::a", status=status, backend=backend, shots=1000,
                           duration_ms=1200.0)],
    )


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #
class TestMigration:
    def test_v1_record_upgrades(self):
        v1 = {"schema": 1, "created_at": "2026-07-10T00:00:00", "status": "pass",
              "tally": {"pass": 1}, "total_shots": 1000, "cheapest_usd": 0.5, "tests": []}
        upgraded = migrate_record(v1)
        assert upgraded["schema"] == HISTORY_SCHEMA
        assert upgraded["execution"] is None
        # migration only adds — original data is untouched
        assert upgraded["cheapest_usd"] == 0.5

    def test_schemaless_record_upgrades(self):
        upgraded = migrate_record({"created_at": "x", "status": "pass", "tests": []})
        assert upgraded["schema"] == HISTORY_SCHEMA and "execution" in upgraded

    def test_v2_record_is_untouched(self):
        v2 = {"schema": 2, "created_at": "x", "status": "pass", "execution": None, "tests": []}
        assert migrate_record(v2) is v2

    def test_migration_does_not_drop_execution(self):
        exe = {"mode": "hardware", "target": "x"}
        v2 = {"schema": 2, "created_at": "x", "status": "pass", "execution": exe, "tests": []}
        assert migrate_record(v2)["execution"] == exe


# --------------------------------------------------------------------------- #
# Read / write round-trip
# --------------------------------------------------------------------------- #
class TestReadWrite:
    def test_append_writes_schema_2(self, tmp_path):
        append_history(tmp_path, _suite())
        (record,) = read_history(tmp_path)
        assert record["schema"] == HISTORY_SCHEMA
        assert record["execution"] is None

    def test_execution_record_round_trips(self, tmp_path):
        exe = ExecutionRecord(mode="hardware", provider="braket",
                              target="braket:ionq_forte", backend="hw:braket:ionq_forte",
                              estimated_cost_usd=1.5, runtime_s=9.0, routing_strategy="value",
                              outcome="pass")
        append_history(tmp_path, _suite(backend="hw:braket:ionq_forte"), cheapest_usd=1.5,
                       execution=exe)
        (record,) = read_history(tmp_path)
        assert record["execution"]["mode"] == "hardware"
        assert record["execution"]["routing_strategy"] == "value"
        assert record["execution"]["estimated_cost_usd"] == 1.5

    def test_old_format_file_still_reads(self, tmp_path):
        # Simulate a file written by an older version (schema 1, no execution).
        path = history_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"schema": 1, "created_at": "2026-07-01T00:00:00",
                                    "status": "pass", "tally": {"pass": 1}, "tests": []}) + "\n")
        (record,) = read_history(tmp_path)
        assert record["schema"] == HISTORY_SCHEMA  # migrated on read
        assert record["execution"] is None


# --------------------------------------------------------------------------- #
# Dashboard v2
# --------------------------------------------------------------------------- #
def _hw_record(status="pass", at="2026-07-12T00:00:00", cost=0.72):
    return {
        "schema": 2, "created_at": at, "status": status,
        "tally": {"pass": 1 if status == "pass" else 0, "fail": 0, "error": 0},
        "total_shots": 2000, "cheapest_usd": cost,
        "execution": {"mode": "hardware", "target": "braket:rigetti_cepheus",
                      "provider": "braket", "routing_strategy": "value",
                      "estimated_cost_usd": cost, "runtime_s": 12.0, "outcome": status},
        "tests": [{"id": "t::a", "status": status, "backend": "hw:braket:rigetti_cepheus",
                   "duration_ms": 12000.0, "checks": [{"name": "c", "statistic": 0.04,
                                                       "threshold": 0.06}]}],
    }


class TestDashboardV2:
    def test_hardware_sections_render(self):
        records = [_hw_record(), _hw_record(status="fail", at="2026-07-13T00:00:00")]
        html_out = render_dashboard(records)
        for section in ("Provider usage", "Provider comparison",
                        "Hardware cost estimate over time", "HW success rate"):
            assert section in html_out

    def test_dashboard_is_self_contained(self):
        html_out = render_dashboard([_hw_record()] * 3)
        assert "http://" not in html_out and "https://" not in html_out
        assert "<script" not in html_out

    def test_simulator_only_omits_hardware_sections(self):
        sim = {"schema": 2, "created_at": "2026-07-12T00:00:00", "status": "pass",
               "tally": {"pass": 1, "fail": 0, "error": 0}, "total_shots": 1000,
               "cheapest_usd": None, "execution": None,
               "tests": [{"id": "t::a", "status": "pass", "backend": "aer", "checks": []}]}
        html_out = render_dashboard([sim, sim])
        assert "Provider usage" not in html_out
        assert "Provider comparison" not in html_out
        assert "Runs recorded" in html_out  # base dashboard still renders
