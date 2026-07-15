"""Quantum Intelligence Network: consent, privacy scrubbing, outbox, sync, community."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from qontinuum import config, telemetry
from qontinuum.cli import app
from qontinuum.intelligence import assess_health
from qontinuum.report.history import ExecutionRecord, append_history
from qontinuum.report.schema import Status, SuiteResult
from qontinuum.report.schema import TestResult as _TestResult
from qontinuum.telemetry.schema import CommunityAggregate, TelemetryRecord, bucket

# Fields that must NEVER appear in a telemetry record, whatever the source.
_FORBIDDEN = {
    "counts", "circuit_hash", "seed", "git_sha", "tests", "checks", "source",
    "distribution", "snapshot", "token", "api_key", "password", "path", "id",
}


def _hw_history(created="2026-07-20T09:00:00", outcome="pass", target="braket:rigetti_cepheus"):
    exe = ExecutionRecord(mode="hardware", provider="braket", target=target,
                          backend=f"hw:{target}", estimated_cost_usd=0.72, runtime_s=12.0,
                          routing_strategy="value", outcome=outcome)
    return {"created_at": created, "tool_version": "0.5.0", "status": outcome,
            "total_shots": 2000, "execution": exe.model_dump(),
            # decoy sensitive fields that must be dropped:
            "git_sha": "deadbeef", "seed": 42,
            "tests": [{"id": "q_test_secret.py::x", "counts": {"00": 1000},
                       "circuit_hash": "sha256:abc", "backend": f"hw:{target}"}]}


# --------------------------------------------------------------------------- #
# Consent — off by default
# --------------------------------------------------------------------------- #
class TestConsent:
    def test_disabled_by_default(self, tmp_path):
        assert telemetry.consent.is_enabled(tmp_path) is False
        assert telemetry.capture(tmp_path, _hw_history()) is False
        assert telemetry.outbox.count(tmp_path) == 0

    def test_enable_mints_install_id(self, tmp_path):
        install = telemetry.consent.enable(tmp_path)
        assert telemetry.consent.is_enabled(tmp_path) is True
        assert len(install) == 36  # uuid4
        # stable across a disable/enable cycle
        telemetry.consent.disable(tmp_path)
        assert telemetry.consent.is_enabled(tmp_path) is False
        assert telemetry.consent.enable(tmp_path) == install

    def test_capture_only_when_enabled(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        assert telemetry.capture(tmp_path, _hw_history()) is True
        assert telemetry.outbox.count(tmp_path) == 1

    def test_simulator_runs_are_not_captured(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        sim = {"created_at": "x", "status": "pass", "total_shots": 1000, "execution": None}
        assert telemetry.capture(tmp_path, sim) is False


# --------------------------------------------------------------------------- #
# Privacy — the allowlist
# --------------------------------------------------------------------------- #
class TestPrivacy:
    def test_no_forbidden_fields_leak(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        telemetry.capture(tmp_path, _hw_history())
        record = telemetry.outbox.read_all(tmp_path)[0]
        dumped = json.dumps(record.model_dump())
        assert _FORBIDDEN & set(record.model_dump().keys()) == set()
        # decoy values must not appear anywhere in the serialized record
        for leak in ("deadbeef", "q_test_secret", "sha256:abc", "\"00\""):
            assert leak not in dumped

    def test_only_allowlisted_fields_present(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        telemetry.capture(tmp_path, _hw_history())
        record = telemetry.outbox.read_all(tmp_path)[0]
        assert set(record.model_dump()) == set(TelemetryRecord.model_fields)

    def test_timestamp_is_day_granularity(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        telemetry.capture(tmp_path, _hw_history(created="2026-07-20T09:37:11"))
        assert telemetry.outbox.read_all(tmp_path)[0].ts_day == "2026-07-20"

    def test_bucketing_coarsens_counts(self):
        assert bucket(7, (10, 50, 100)) == "1-10"
        assert bucket(50, (10, 50, 100)) == "11-50"
        assert bucket(250, (10, 50, 100)) == "101+"

    def test_preview_matches_what_would_send(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        previews = telemetry.preview(tmp_path, [_hw_history(), _hw_history(outcome="fail")])
        assert len(previews) == 2
        assert {p.outcome for p in previews} == {"pass", "fail"}


# --------------------------------------------------------------------------- #
# Integrity + outbox
# --------------------------------------------------------------------------- #
class TestIntegrity:
    def test_records_are_signed_and_verify(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        telemetry.capture(tmp_path, _hw_history())
        record = telemetry.outbox.read_all(tmp_path)[0]
        assert record.checksum and record.verify()

    def test_tampered_record_is_dropped_on_read(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        telemetry.capture(tmp_path, _hw_history())
        path = telemetry.outbox.outbox_path(tmp_path)
        data = json.loads(path.read_text().strip())
        data["outcome"] = "fail"  # tamper without re-signing
        path.write_text(json.dumps(data) + "\n")
        assert telemetry.outbox.read_all(tmp_path) == []  # integrity check drops it

    def test_clear_empties_outbox(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        telemetry.capture(tmp_path, _hw_history())
        assert telemetry.outbox.clear(tmp_path) == 1
        assert telemetry.outbox.count(tmp_path) == 0


# --------------------------------------------------------------------------- #
# Sync — graceful offline
# --------------------------------------------------------------------------- #
class TestSync:
    def test_sync_noop_when_disabled(self, tmp_path):
        result = telemetry.sync(tmp_path)
        assert result.ok is False and "disabled" in result.detail

    def test_no_endpoint_keeps_queue(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        telemetry.capture(tmp_path, _hw_history())
        result = telemetry.sync(tmp_path)
        assert result.ok and result.sent == 0 and result.queued == 1

    def test_insecure_endpoint_refused(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        config.set_value(tmp_path, "telemetry.endpoint", "http://insecure.example")
        telemetry.capture(tmp_path, _hw_history())
        result = telemetry.sync(tmp_path)
        assert result.ok is False and "https" in result.detail
        assert telemetry.outbox.count(tmp_path) == 1  # not sent

    def test_offline_keeps_queue(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        config.set_value(tmp_path, "telemetry.endpoint", "https://net.example")
        telemetry.capture(tmp_path, _hw_history())

        def boom(url, payload, timeout):
            raise OSError("no network")

        result = telemetry.sync(tmp_path, transport=boom)
        assert result.ok is False and telemetry.outbox.count(tmp_path) == 1

    def test_successful_sync_clears_and_caches_community(self, tmp_path):
        telemetry.consent.enable(tmp_path)
        config.set_value(tmp_path, "telemetry.endpoint", "https://net.example")
        telemetry.capture(tmp_path, _hw_history())

        def ok(url, payload, timeout):
            assert url == "https://net.example/contribute"
            assert payload["records"] and "install_id" in payload
            return {"community": {"schema_version": 1, "generated_at": "2026-07-20",
                                  "devices": {"braket:rigetti_cepheus": {"samples": 90,
                                              "success_rate": 0.8}}}}

        result = telemetry.sync(tmp_path, transport=ok)
        assert result.ok and result.sent == 1 and result.community_updated
        assert telemetry.outbox.count(tmp_path) == 0
        assert telemetry.load_community(tmp_path).devices["braket:rigetti_cepheus"].samples == 90


# --------------------------------------------------------------------------- #
# Community intelligence blends into health
# --------------------------------------------------------------------------- #
class TestCommunityBlend:
    def test_community_adds_signal_to_health(self):
        from qontinuum.cost import load_catalog

        agg = CommunityAggregate.model_validate(
            {"schema_version": 1, "generated_at": "x",
             "devices": {"braket:rigetti_cepheus": {"samples": 200, "success_rate": 0.6}}})
        healths = assess_health(load_catalog(), community=agg)
        rig = next(h for h in healths if h.device == "rigetti_cepheus")
        assert "community" in rig.data_sources
        assert rig.community_success == 0.6 and rig.community_samples == 200

    def test_absent_community_is_offline_identical(self):
        from qontinuum.cost import load_catalog

        catalog = load_catalog()
        a = assess_health(catalog)
        b = assess_health(catalog, community=None)
        assert [h.reliability for h in a] == [h.reliability for h in b]
        assert all("community" not in h.data_sources for h in a)

    def test_incompatible_community_snapshot_ignored(self, tmp_path):
        agg = CommunityAggregate(schema_version=999, generated_at="x")
        with pytest.raises(ValueError, match="not supported"):
            telemetry.community.save(tmp_path, agg)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
class TestTelemetryCli:
    def setup_method(self):
        self.runner = CliRunner()

    def test_status_default_off(self, tmp_path):
        result = self.runner.invoke(app, ["telemetry", "status", "--path", str(tmp_path), "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["enabled"] is False

    def test_enable_states_what_is_shared(self, tmp_path):
        result = self.runner.invoke(app, ["telemetry", "enable", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "never share" in result.output.lower()
        assert "credentials" in result.output.lower()

    def test_preview_and_sync_flow(self, tmp_path):
        # write a hardware history record, then enable + preview
        suite = SuiteResult(tool_version="0.5.0", tests=[
            _TestResult(id="t::a", status=Status.PASS, backend="hw:braket:ionq_forte",
                       shots=2000, duration_ms=9000.0)])
        exe = ExecutionRecord(mode="hardware", provider="braket", target="braket:ionq_forte",
                              backend="hw:braket:ionq_forte", estimated_cost_usd=1.5,
                              runtime_s=9.0, outcome="pass")
        append_history(tmp_path, suite, cheapest_usd=1.5, execution=exe)
        self.runner.invoke(app, ["telemetry", "enable", "--path", str(tmp_path)])
        preview = self.runner.invoke(
            app, ["telemetry", "preview", "--path", str(tmp_path), "--json"])
        rows = json.loads(preview.output)
        assert rows and rows[0]["device"] == "braket:ionq_forte"
        sync = self.runner.invoke(app, ["telemetry", "sync", "--path", str(tmp_path), "--json"])
        assert json.loads(sync.output)["ok"] is True  # no endpoint -> local no-op
