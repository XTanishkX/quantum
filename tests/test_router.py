import pytest
from qiskit import QuantumCircuit

from qontinuum.cost import estimate_suite, load_catalog, profile_circuit
from qontinuum.router import RouteScore, rank, score_devices, success_probability


def bell() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


def deep(n_qubits=10, layers=30) -> QuantumCircuit:
    qc = QuantumCircuit(n_qubits)
    for _ in range(layers):
        for i in range(n_qubits - 1):
            qc.cx(i, i + 1)
    qc.measure_all()
    return qc


QUALITY = {
    "error_1q": 0.001,
    "error_2q": 0.01,
    "error_readout": 0.02,
    "connectivity": "all_to_all",
}


class TestSuccessProbability:
    def test_bell_hand_computed(self):
        p = success_probability(profile_circuit(bell()), QUALITY)
        # (1-.001)^1 * (1-.01)^1 * (1-.02)^2
        assert p == pytest.approx(0.999 * 0.99 * 0.98**2, rel=1e-9)

    def test_routing_overhead_only_beyond_two_qubits(self):
        sparse = dict(QUALITY, connectivity="linear")
        two_qubit = profile_circuit(bell())
        assert success_probability(two_qubit, sparse) == pytest.approx(
            success_probability(two_qubit, QUALITY)
        )
        wide = profile_circuit(deep(n_qubits=5, layers=2))
        assert success_probability(wide, sparse) < success_probability(wide, QUALITY)

    def test_deep_circuits_decay(self):
        assert success_probability(profile_circuit(deep()), QUALITY) < 0.1


class TestScoreAndRank:
    def scores(self, circuits_shots):
        catalog = load_catalog()
        profiles = [profile_circuit(qc) for qc, _ in circuits_shots]
        return score_devices(profiles, estimate_suite(circuits_shots), catalog)

    def test_every_catalog_device_scored(self):
        scores = self.scores([(bell(), 1000)])
        catalog = load_catalog()
        n_devices = sum(len(p["devices"]) for p in catalog["providers"].values())
        assert len(scores) == n_devices
        feasible = [s for s in scores if s.feasible]
        assert all(s.success_prob is not None for s in feasible)

    def test_rank_by_cost_puts_rigetti_first_for_bell(self):
        ranked = rank(self.scores([(bell(), 1000)]), optimize="cost")
        assert ranked[0].device == "rigetti_cepheus"

    def test_rank_by_fidelity_prefers_quantinuum(self):
        ranked = rank(self.scores([(bell(), 1000)]), optimize="fidelity")
        assert ranked[0].device == "quantinuum_h2"

    def test_value_ranking_balances_both(self):
        # For a deep circuit, cheap-but-noisy loses ground to costlier-but-cleaner.
        by_cost = rank(self.scores([(deep(), 1000)]), optimize="cost")
        by_value = rank(self.scores([(deep(), 1000)]), optimize="value")
        cost_rank = [s.device for s in by_cost]
        value_rank = [s.device for s in by_value]
        assert cost_rank[0] == "rigetti_cepheus"
        assert value_rank.index("rigetti_cepheus") > 0

    def test_infeasible_devices_rank_last(self):
        wide = QuantumCircuit(60)
        wide.h(0)
        wide.measure_all()
        ranked = rank(self.scores([(wide, 100)]), optimize="value")
        feasibility = [s.feasible for s in ranked]
        assert feasibility == sorted(feasibility, reverse=True)

    def test_unknown_optimize_target_rejected(self):
        with pytest.raises(ValueError, match="optimize"):
            rank([RouteScore(provider="p", device="d", display="D")], optimize="vibes")


def test_usd_per_success_property():
    s = RouteScore(provider="p", device="d", display="D", success_prob=0.5, usd=10.0)
    assert s.usd_per_success == pytest.approx(20.0)
    assert RouteScore(provider="p", device="d", display="D").usd_per_success is None
