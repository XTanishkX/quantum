import json
import xml.etree.ElementTree as ET

from qontinuum.cli import app


class TestReportGroup:
    def test_junit_valid_xml(self, runner, mini_project, tmp_path):
        out = tmp_path / "junit.xml"
        result = runner.invoke(
            app, ["report", "junit", "--path", str(mini_project), "--seed", "3",
                  "--out", str(out)]
        )
        assert result.exit_code == 0
        root = ET.fromstring(out.read_text())
        assert root.tag == "testsuite"
        assert root.attrib["failures"] == "0"
        assert root.find("testcase").attrib["name"] == "entangled"

    def test_junit_failure_case(self, runner, tmp_path):
        (tmp_path / "q_test_bad.py").write_text(
            "from qiskit import QuantumCircuit\n"
            "from qontinuum import qtest, assert_probability\n"
            "@qtest(shots=500)\n"
            "def coin():\n"
            "    qc = QuantumCircuit(1)\n"
            "    qc.h(0)\n"
            "    qc.measure_all()\n"
            "    return qc\n"
            "@coin.check\n"
            "def impossible(result):\n"
            "    assert_probability(result, '0', min_p=0.99)\n"
        )
        out = tmp_path / "junit.xml"
        runner.invoke(app, ["report", "junit", "--path", str(tmp_path), "--out", str(out)])
        root = ET.fromstring(out.read_text())
        assert root.attrib["failures"] == "1"
        assert root.find("testcase/failure") is not None

    def test_badge_states(self, runner, mini_project, tmp_path):
        out = tmp_path / "b.svg"
        runner.invoke(app, ["report", "badge", "--path", str(mini_project),
                            "--seed", "3", "--out", str(out)])
        assert "passing" in out.read_text()

    def test_summary_line(self, runner, mini_project):
        result = runner.invoke(app, ["report", "summary", "--path", str(mini_project),
                                     "--seed", "3"])
        assert result.output.startswith("status=pass pass=1")

    def test_report_from_saved_suite(self, runner, mini_project, tmp_path):
        suite_json = tmp_path / "s.json"
        runner.invoke(app, ["test", str(mini_project), "--seed", "3",
                            "--json", str(suite_json), "--no-history"])
        result = runner.invoke(app, ["report", "md", "--from", str(suite_json)])
        assert result.exit_code == 0
        assert "Qontinuum report" in result.output


class TestPack:
    def test_create_inspect_verify_roundtrip(self, runner, mini_project, tmp_path):
        bundle = tmp_path / "p.tar.gz"
        create = runner.invoke(app, ["pack", "create", str(mini_project),
                                     "--out", str(bundle)])
        assert create.exit_code == 0
        inspect = runner.invoke(app, ["pack", "inspect", str(bundle), "--json"])
        data = json.loads(inspect.output)
        assert data["tests"] == 1 and data["seed"] == 42
        verify = runner.invoke(app, ["pack", "verify", str(bundle)])
        assert verify.exit_code == 0
        assert "reproduces" in verify.output

    def test_verify_detects_changed_circuit(self, runner, mini_project, tmp_path):
        bundle = tmp_path / "p.tar.gz"
        runner.invoke(app, ["pack", "create", str(mini_project), "--out", str(bundle)])
        # verify against a *tampered* bundle: rewrite packed test with new circuit
        import io
        import tarfile

        with tarfile.open(bundle) as tar:
            manifest = json.loads(tar.extractfile("qontinuum-pack.json").read())
            source = tar.extractfile("suite/q_test_bell.py").read().decode()
        source = source.replace("qc.cx(0, 1)", "qc.cx(0, 1)\n    qc.x(0)")
        with tarfile.open(bundle, "w:gz") as tar:
            for name, data in [("qontinuum-pack.json", json.dumps(manifest).encode()),
                               ("suite/q_test_bell.py", source.encode())]:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        verify = runner.invoke(app, ["pack", "verify", str(bundle)])
        assert verify.exit_code == 1
        assert "CIRCUIT CHANGED" in verify.output

    def test_empty_dir_rejected(self, runner, tmp_path):
        result = runner.invoke(app, ["pack", "create", str(tmp_path),
                                     "--out", str(tmp_path / "p.tar.gz")])
        assert result.exit_code == 2


class TestRegistryCli:
    def test_lifecycle(self, runner, mini_project):
        qasm = str(mini_project / "bell.qasm")
        base = ["--path", str(mini_project)]
        assert runner.invoke(app, ["registry", "add", qasm, "--name", "bell", *base]).exit_code == 0
        # same hash again -> error
        assert runner.invoke(app, ["registry", "add", qasm, "--name", "bell", *base]).exit_code == 2
        listing = runner.invoke(app, ["registry", "list", *base, "--json"])
        assert json.loads(listing.output)[0]["name"] == "bell"
        assert runner.invoke(app, ["registry", "tag", "bell", "prod", *base]).exit_code == 0
        log = runner.invoke(app, ["registry", "log", "bell", *base, "--json"])
        assert json.loads(log.output)[0]["tags"] == ["prod"]
        assert runner.invoke(app, ["registry", "rm", "bell", "--yes", *base]).exit_code == 0


class TestSnapshotGroup:
    def test_list_show_rm_prune(self, runner, tmp_path):
        (tmp_path / "q_test_s.py").write_text(
            "from qiskit import QuantumCircuit\n"
            "from qontinuum import qtest\n"
            "@qtest(shots=500, snapshot=True)\n"
            "def ghz():\n"
            "    qc = QuantumCircuit(2)\n"
            "    qc.h(0)\n"
            "    qc.cx(0, 1)\n"
            "    qc.measure_all()\n"
            "    return qc\n"
        )
        runner.invoke(app, ["snapshot", "update", str(tmp_path)])
        listing = runner.invoke(app, ["snapshot", "list", str(tmp_path), "--json"])
        rows = json.loads(listing.output)
        assert len(rows) == 1
        test_id = rows[0]["test"]
        show = runner.invoke(app, ["snapshot", "show", test_id, str(tmp_path), "--json"])
        assert "counts" in json.loads(show.output)
        # prune with test file still present: nothing pruned
        prune = runner.invoke(app, ["snapshot", "prune", str(tmp_path)])
        assert "no stale" in prune.output
        # remove the test file -> prune drops it
        (tmp_path / "q_test_s.py").unlink()
        prune = runner.invoke(app, ["snapshot", "prune", str(tmp_path)])
        assert "pruned" in prune.output


class TestShotsAndStats:
    def test_shots_for_tvd_matches_floor(self, runner):
        shots = json.loads(
            runner.invoke(app, ["shots", "for-tvd", "0.05", "--json"]).output
        )["min_shots"]
        floor = json.loads(
            runner.invoke(app, ["shots", "floor", str(shots), "--json"]).output
        )["min_sound_tvd_threshold"]
        assert floor <= 0.05

    def test_shots_plan_flags_unsound(self, runner, tmp_path):
        (tmp_path / "q_test_u.py").write_text(
            "from qiskit import QuantumCircuit\n"
            "from qontinuum import qtest, assert_distribution\n"
            "@qtest(shots=200)\n"
            "def tight():\n"
            "    qc = QuantumCircuit(1)\n"
            "    qc.h(0)\n"
            "    qc.measure_all()\n"
            "    return qc\n"
            "@tight.check\n"
            "def check(result):\n"
            "    assert_distribution(result, {'0': .5, '1': .5}, tvd_threshold=0.01)\n"
        )
        assert runner.invoke(app, ["shots", "plan", str(tmp_path)]).exit_code == 1

    def test_stats_compare_same_source(self, runner, tmp_path):
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        a.write_text('{"00": 5000, "11": 5000}')
        b.write_text('{"00": 4980, "11": 5020}')
        assert runner.invoke(app, ["stats", "compare", str(a), str(b)]).exit_code == 0

    def test_stats_tvd_flags_floor(self, runner, tmp_path):
        c = tmp_path / "c.json"
        c.write_text('{"00": 30, "11": 20}')
        result = runner.invoke(
            app, ["stats", "tvd", str(c), "--expected", '{"00":0.5,"11":0.5}', "--json"]
        )
        data = json.loads(result.output)
        assert data["sampling_floor_99"] > 0.1  # 50 shots resolve very little


class TestMockFuzz:
    def test_mock_deterministic(self, runner, tmp_path):
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        for out in (a, b):
            runner.invoke(app, ["mock", "--state", "ghz", "--qubits", "3",
                                "--shots", "500", "--seed", "9", "--out", str(out)])
        assert a.read_text() == b.read_text()
        counts = json.loads(a.read_text())
        assert set(counts) <= {"000", "111"}

    def test_mock_noise_leaks(self, runner, tmp_path):
        out = tmp_path / "n.json"
        runner.invoke(app, ["mock", "--state", "zeros", "--qubits", "2",
                            "--shots", "500", "--noise", "0.4", "--out", str(out)])
        counts = json.loads(out.read_text())
        assert set(counts) != {"00"}

    def test_fuzz_stable_test_passes(self, runner, mini_project):
        result = runner.invoke(
            app, ["fuzz", str(mini_project), "--trials", "4", "--min-pass-rate", "0.5"]
        )
        assert result.exit_code == 0

    def test_explain_passing_test(self, runner, mini_project):
        result = runner.invoke(
            app, ["explain", "bell", "--path", str(mini_project), "--seed", "3", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["failing_checks"] is None
