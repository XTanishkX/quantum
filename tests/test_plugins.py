"""Plugin discovery, resolution, and the `qont plugin` CLI."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from qontinuum.circuits import CircuitLoadError, load_circuit
from qontinuum.cli import app
from qontinuum.hardware import HardwareError, resolve_adapter
from qontinuum.plugins import PluginError, PluginRecord, get_registry
from qontinuum.plugins import registry as registry_mod
from qontinuum.plugins.registry import PluginRegistry
from qontinuum.runner.backends import BackendSpecError, resolve_backend

# --------------------------------------------------------------------------- #
# Test doubles
# --------------------------------------------------------------------------- #


class FakeEntryPoint:
    """Minimal stand-in for importlib.metadata.EntryPoint."""

    def __init__(self, name, loader, dist_name="fake-dist"):
        self.name = name
        self.group = ""
        self._loader = loader
        self.dist = type("Dist", (), {"name": dist_name})()

    def load(self):
        return self._loader()


class FakeSDK:
    name = "toy"
    requires = ()
    summary = "a toy SDK that recognizes Sentinel objects"

    def matches(self, source):
        return type(source).__name__ == "Sentinel"

    def to_qiskit(self, source):
        from qiskit import QuantumCircuit

        qc = QuantumCircuit(1)
        qc.h(0)
        qc.measure_all()
        return qc


class FakeProviderWithCatalog:
    name = "acme"
    catalog_key = "acme"
    requires = ()
    summary = "toy provider that also prices its own device"

    def build_adapter(self, device):  # pragma: no cover - not exercised here
        raise HardwareError("acme has no real adapter")

    def catalog_fragment(self):
        return {
            "display": "ACME Quantum",
            "devices": {
                "acme_one": {
                    "display": "ACME One",
                    "qubits": 20,
                    "model": "per_shot",
                    "per_task": 0.10,
                    "per_shot": 0.001,
                }
            },
        }


@pytest.fixture
def patched_entry_points(monkeypatch):
    """Install fake entry points and hand back a fresh registry each call."""

    def install(groups: dict[str, list[FakeEntryPoint]]):
        def fake_entry_points(*, group):
            return list(groups.get(group, []))

        monkeypatch.setattr(registry_mod.metadata, "entry_points", fake_entry_points)
        reg = PluginRegistry()
        return reg

    return install


@pytest.fixture
def refresh_singleton():
    """Ensure the process-wide registry is rebuilt before and after a test."""
    get_registry().refresh()
    yield
    get_registry().refresh()


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def test_builtins_are_always_discovered():
    reg = PluginRegistry()
    assert set(reg.names("provider")) >= {"ibm", "braket"}
    assert set(reg.names("backend")) >= {"aer", "ibm"}
    assert set(reg.names("sdk")) >= {"qiskit", "cirq", "pennylane"}
    assert all(r.source == "builtin" for r in reg.records_for("sdk"))


def test_entry_point_plugin_is_loaded(patched_entry_points):
    reg = patched_entry_points({"qontinuum.sdks": [FakeEntryPoint("toy", FakeSDK)]})
    rec = reg.get("sdk", "toy")
    assert rec is not None
    assert rec.available and rec.source == "entrypoint"
    assert rec.dist == "fake-dist"
    assert isinstance(reg.require("sdk", "toy"), FakeSDK)


def test_broken_plugin_is_recorded_not_fatal(patched_entry_points):
    def explode():
        raise ImportError("no module named nope")

    reg = patched_entry_points(
        {"qontinuum.sdks": [FakeEntryPoint("busted", explode)]}
    )
    rec = reg.get("sdk", "busted")
    assert rec is not None and not rec.available
    assert "ImportError" in rec.error
    # discovery still surfaced the built-ins
    assert "qiskit" in reg.names("sdk")
    with pytest.raises(PluginError, match="failed to load"):
        reg.require("sdk", "busted")


def test_entry_point_shadows_builtin(patched_entry_points):
    class ShadowSDK(FakeSDK):
        name = "qiskit"  # deliberately collides with the built-in

    reg = patched_entry_points(
        {"qontinuum.sdks": [FakeEntryPoint("qiskit", ShadowSDK)]}
    )
    rec = reg.get("sdk", "qiskit")
    assert rec.source == "entrypoint"
    assert rec.shadows == "builtin"
    assert isinstance(reg.require("sdk", "qiskit"), ShadowSDK)


def test_require_unknown_lists_known():
    with pytest.raises(PluginError, match="known:"):
        PluginRegistry().require("provider", "nope")


# --------------------------------------------------------------------------- #
# Backwards compatibility of the refactored dispatch points
# --------------------------------------------------------------------------- #


class TestResolveAdapterCompat:
    def test_missing_provider_prefix(self):
        with pytest.raises(HardwareError, match="expected"):
            resolve_adapter("ibm_brisbane")

    def test_unknown_provider(self):
        with pytest.raises(HardwareError, match="unknown hardware provider"):
            resolve_adapter("dwave:advantage")

    def test_unknown_braket_device_bubbles_up(self):
        with pytest.raises(HardwareError, match="available"):
            resolve_adapter("braket:not_a_device")


class TestResolveBackendCompat:
    def test_aer(self):
        from qiskit_aer import AerSimulator

        assert isinstance(resolve_backend("aer"), AerSimulator)

    def test_ibm_noise(self):
        # bundled fake-provider calibration, no account/network needed
        backend = resolve_backend("ibm:fake_manila")
        assert backend is not None

    def test_unknown_backend(self):
        with pytest.raises(BackendSpecError, match="unknown backend spec"):
            resolve_backend("qsim")


class TestLoadCircuitCompat:
    def test_qasm_string_still_loads(self):
        qasm = (
            'OPENQASM 3.0;\ninclude "stdgates.inc";\n'
            "qubit[2] q;\nbit[2] c;\nh q[0];\ncx q[0], q[1];\nc = measure q;\n"
        )
        assert load_circuit(qasm).num_qubits == 2

    def test_unsupported_object_rejected(self):
        with pytest.raises(CircuitLoadError, match="Unsupported circuit source"):
            load_circuit(42)


def test_third_party_sdk_plugin_drives_load_circuit(
    patched_entry_points, monkeypatch, refresh_singleton
):
    """A registered SDK plugin converts a foreign object through load_circuit."""
    monkeypatch.setattr(
        registry_mod.metadata,
        "entry_points",
        lambda *, group: [FakeEntryPoint("toy", FakeSDK)]
        if group == "qontinuum.sdks"
        else [],
    )
    get_registry().refresh()

    class Sentinel:
        pass

    qc = load_circuit(Sentinel())
    assert qc.num_qubits == 1 and qc.num_clbits == 1


# --------------------------------------------------------------------------- #
# Catalog fragment merge
# --------------------------------------------------------------------------- #


def test_catalog_merge_is_noop_without_fragments():
    from qontinuum.cost.estimator import load_catalog

    load_catalog.cache_clear()
    try:
        catalog = load_catalog()
        assert "acme" not in catalog["providers"]
        assert {"braket", "ibm"} <= set(catalog["providers"])
    finally:
        load_catalog.cache_clear()


def test_provider_plugin_contributes_catalog_devices(
    patched_entry_points, monkeypatch, refresh_singleton
):
    from qontinuum.cost.estimator import load_catalog

    monkeypatch.setattr(
        registry_mod.metadata,
        "entry_points",
        lambda *, group: [FakeEntryPoint("acme", FakeProviderWithCatalog)]
        if group == "qontinuum.providers"
        else [],
    )
    get_registry().refresh()
    load_catalog.cache_clear()
    try:
        catalog = load_catalog()
        assert "acme" in catalog["providers"]
        assert "acme_one" in catalog["providers"]["acme"]["devices"]
    finally:
        load_catalog.cache_clear()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


class TestPluginCli:
    def setup_method(self):
        self.runner = CliRunner()

    def test_list_table(self):
        result = self.runner.invoke(app, ["plugin", "list"])
        assert result.exit_code == 0
        assert "ibm" in result.output and "qiskit" in result.output

    def test_list_json_filtered(self):
        import json

        result = self.runner.invoke(app, ["plugin", "list", "--kind", "sdk", "--json"])
        assert result.exit_code == 0
        rows = json.loads(result.output)
        assert {r["kind"] for r in rows} == {"sdk"}
        assert {"qiskit", "cirq", "pennylane"} <= {r["name"] for r in rows}

    def test_show_disambiguates_by_kind(self):
        # "ibm" exists as both a provider and a backend
        ambiguous = self.runner.invoke(app, ["plugin", "show", "ibm"])
        assert ambiguous.exit_code == 2
        assert "ambiguous" in ambiguous.output

        ok = self.runner.invoke(app, ["plugin", "show", "ibm", "--kind", "backend"])
        assert ok.exit_code == 0
        assert "IBMNoiseBackend" in ok.output

    def test_show_unknown(self):
        result = self.runner.invoke(app, ["plugin", "show", "nope"])
        assert result.exit_code == 2

    def test_doctor_healthy_env_exits_zero(self):
        result = self.runner.invoke(app, ["plugin", "doctor"])
        assert result.exit_code == 0
        assert "ready" in result.output.lower()

    def test_doctor_fails_when_builtin_broken(self, monkeypatch):
        broken = PluginRecord(
            name="core", kind="backend", source="builtin", available=False,
            error="boom",
        )

        class Stub:
            def records(self):
                return [broken]

        import qontinuum.plugins as plugins_pkg

        monkeypatch.setattr(plugins_pkg, "get_registry", lambda: Stub())
        result = self.runner.invoke(app, ["plugin", "doctor"])
        assert result.exit_code == 1
