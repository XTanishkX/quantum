import json

import pytest

from qontinuum import config
from qontinuum.cli import app
from qontinuum.cli_util import read_counts_file


class TestConfig:
    def test_set_get_roundtrip(self, tmp_path):
        config.set_value(tmp_path, "defaults.seed", "42")
        assert config.get(tmp_path, "defaults.seed") == 42
        assert config.config_path(tmp_path).is_file()

    def test_unknown_key_rejected(self, tmp_path):
        with pytest.raises(config.ConfigError, match="valid keys"):
            config.set_value(tmp_path, "nope.nope", "1")

    def test_unset_reverts_to_default(self, tmp_path):
        config.set_value(tmp_path, "cache.enabled", "true")
        assert config.get(tmp_path, "cache.enabled") is True
        config.unset(tmp_path, "cache.enabled")
        assert config.get(tmp_path, "cache.enabled") is False

    def test_list_values_parse(self, tmp_path):
        config.set_value(tmp_path, "lint.ignore", '["Q003", "Q007"]')
        assert config.get(tmp_path, "lint.ignore") == ["Q003", "Q007"]

    def test_effective_merges_defaults(self, tmp_path):
        values = config.effective(tmp_path)
        assert set(values) == set(config.KNOWN_KEYS)

    def test_cli_get_set_list(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert runner.invoke(app, ["config", "set", "defaults.seed", "9"]).exit_code == 0
        result = runner.invoke(app, ["config", "get", "defaults.seed"])
        assert result.output.strip() == "9"
        listing = runner.invoke(app, ["config", "list", "--json"])
        rows = json.loads(listing.output)
        assert any(r["key"] == "defaults.seed" and r["source"] == "project" for r in rows)

    def test_cli_unknown_key_exits_2(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert runner.invoke(app, ["config", "get", "bogus.key"]).exit_code == 2


class TestReadCountsFile:
    def test_flat_counts(self, tmp_path):
        f = tmp_path / "c.json"
        f.write_text('{"00": 5, "11": 7}')
        assert read_counts_file(f) == {"00": 5, "11": 7}

    def test_counts_key_unwrapped(self, tmp_path):
        f = tmp_path / "c.json"
        f.write_text('{"counts": {"0": 3}, "shots": 3}')
        assert read_counts_file(f) == {"0": 3}

    def test_garbage_rejected(self, tmp_path):
        import typer

        f = tmp_path / "c.json"
        f.write_text('{"00": "many"}')
        with pytest.raises(typer.Exit):
            read_counts_file(f)


class TestInit:
    def test_scaffolds_project(self, runner, tmp_path):
        result = runner.invoke(app, ["init", str(tmp_path), "--action"])
        assert result.exit_code == 0
        assert (tmp_path / "q_test_example.py").is_file()
        assert (tmp_path / ".qontinuum" / "config.toml").is_file()
        assert (tmp_path / ".github" / "workflows" / "quantum.yml").is_file()
        assert ".qontinuum/cache/" in (tmp_path / ".gitignore").read_text()

    def test_idempotent(self, runner, tmp_path):
        runner.invoke(app, ["init", str(tmp_path)])
        second = runner.invoke(app, ["init", str(tmp_path)])
        assert second.exit_code == 0
        assert "nothing to do" in second.output


class TestDoctorEnv:
    def test_doctor_passes_in_dev_env(self, runner):
        result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0
        checks = json.loads(result.output)
        assert not [c for c in checks if c["status"] == "FAIL"]

    def test_env_lock_and_diff(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert runner.invoke(app, ["env", "lock"]).exit_code == 0
        assert runner.invoke(app, ["env", "diff"]).exit_code == 0

    def test_env_diff_detects_drift(self, runner, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["env", "lock"])
        lock = tmp_path / ".qontinuum" / "env.lock.json"
        data = json.loads(lock.read_text())
        data["qiskit"] = "0.0.1"
        lock.write_text(json.dumps(data))
        result = runner.invoke(app, ["env", "diff"])
        assert result.exit_code == 1
        assert "qiskit" in result.output


class TestSchedule:
    def test_nightly_workflow_written(self, runner, tmp_path):
        out = tmp_path / "w.yml"
        result = runner.invoke(app, ["schedule", "nightly", "--out", str(out)])
        assert result.exit_code == 0
        text = out.read_text()
        assert "cron" in text and "0 3 * * *" in text and "qont ci" in text


def test_version_flag(runner):
    import qontinuum

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert qontinuum.__version__ in result.output
