import json

from qontinuum.cli import app


class TestCircuitGroup:
    def test_stats(self, runner, mini_project):
        result = runner.invoke(
            app, ["circuit", "stats", str(mini_project / "bell.qasm"), "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["qubits"] == 2 and data["gates_2q"] == 1
        assert data["hash"].startswith("sha256:")

    def test_canon_and_hash(self, runner, mini_project):
        qasm = str(mini_project / "bell.qasm")
        canon = runner.invoke(app, ["circuit", "canon", qasm])
        assert json.loads(canon.output)["format"] == "qontinuum-canon-1"
        digest = runner.invoke(app, ["circuit", "hash", qasm])
        assert digest.output.strip().startswith("sha256:")

    def test_convert_roundtrip(self, runner, mini_project, tmp_path):
        out = tmp_path / "bell2.qasm"
        result = runner.invoke(
            app, ["circuit", "convert", str(mini_project / "bell.qasm"),
                  "--to", "qasm2", "--out", str(out)]
        )
        assert result.exit_code == 0
        assert "OPENQASM 2.0" in out.read_text()

    def test_equiv_same_circuit(self, runner, mini_project):
        qasm = str(mini_project / "bell.qasm")
        assert runner.invoke(app, ["circuit", "equiv", qasm, qasm]).exit_code == 0

    def test_equiv_detects_difference(self, runner, mini_project, tmp_path):
        other = tmp_path / "x.qasm"
        other.write_text(
            (mini_project / "bell.qasm").read_text().replace("h q[0];", "x q[0];")
        )
        result = runner.invoke(
            app, ["circuit", "equiv", str(mini_project / "bell.qasm"), str(other)]
        )
        assert result.exit_code == 1

    def test_mirror_emits_inverse(self, runner, mini_project, tmp_path):
        out = tmp_path / "m.qasm"
        result = runner.invoke(
            app, ["circuit", "mirror", str(mini_project / "bell.qasm"), "--out", str(out)]
        )
        assert result.exit_code == 0
        assert "OPENQASM" in out.read_text()

    def test_random_reproducible(self, runner, tmp_path):
        a, b = tmp_path / "a.qasm", tmp_path / "b.qasm"
        runner.invoke(app, ["circuit", "random", "--seed", "3", "--out", str(a)])
        runner.invoke(app, ["circuit", "random", "--seed", "3", "--out", str(b)])
        assert a.read_text() == b.read_text()

    def test_show_draws(self, runner, mini_project):
        result = runner.invoke(app, ["circuit", "show", str(mini_project / "bell.qasm")])
        assert result.exit_code == 0
        assert "q" in result.output


class TestDeviceGroup:
    def test_list_covers_catalog(self, runner):
        result = runner.invoke(app, ["device", "list", "--json"])
        rows = json.loads(result.output)
        ids = {r["id"] for r in rows}
        assert {"rigetti_cepheus", "heron_payg", "quantinuum_h2"} <= ids

    def test_show_known_device(self, runner):
        result = runner.invoke(app, ["device", "show", "rigetti_cepheus", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output)["per_shot"] == 0.000425

    def test_show_unknown_device_exits_2(self, runner):
        assert runner.invoke(app, ["device", "show", "nope"]).exit_code == 2

    def test_compare(self, runner):
        result = runner.invoke(app, ["device", "compare", "iqm_garnet", "ionq_forte"])
        assert result.exit_code == 0
        assert "iqm_garnet" in result.output

    def test_topology(self, runner):
        result = runner.invoke(app, ["device", "topology", "heron_payg"])
        assert result.exit_code == 0
        assert "heavy" in result.output.lower()

    def test_best_respects_budget(self, runner):
        result = runner.invoke(
            app, ["device", "best", "--qubits", "2", "--budget", "1", "--json"]
        )
        rows = json.loads(result.output)
        assert rows and all(r["usd_1000_shots"] <= 1 for r in rows)


class TestProviders:
    def test_list_shows_provenance(self, runner):
        result = runner.invoke(app, ["providers", "list", "--json"])
        rows = json.loads(result.output)
        assert {r["provider"] for r in rows} == {"AWS Braket", "IBM Quantum", "Azure Quantum"}
        assert all(r["verified"] for r in rows)
