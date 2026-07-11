import pytest
from qiskit import QuantumCircuit

from qontinuum.cost import estimate_circuit, estimate_suite, load_catalog, profile_circuit


def bell() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


def by_device(estimates, device):
    return next(e for e in estimates if e.device == device)


class TestProfile:
    def test_bell_profile(self):
        p = profile_circuit(bell())
        assert p.num_qubits == 2
        assert p.n_1q_gates == 1  # h
        assert p.n_2q_gates == 1  # cx
        assert p.n_spam == 4  # 2 implicit preps + 2 measures
        assert p.n_multi_qubit_gates_expanded == 0

    def test_multi_controlled_gate_expansion(self):
        qc = QuantumCircuit(4)
        qc.mcx([0, 1, 2], 3)  # 4 qubits involved -> 6*(4-2) = 12 effective 2q gates
        qc.measure_all()
        p = profile_circuit(qc)
        assert p.n_multi_qubit_gates_expanded == 12
        assert p.n_2q_effective == 12

    def test_barriers_and_delays_ignored(self):
        qc = bell()
        qc.barrier()
        assert profile_circuit(qc).n_1q_gates == 1


class TestEstimates:
    """Hand-computed cross-checks against published provider pricing."""

    def test_braket_per_shot_pricing(self):
        est = estimate_circuit(bell(), shots=4000)
        # IonQ Forte: $0.30/task + 4000 * $0.08/shot
        assert by_device(est, "ionq_forte").usd == pytest.approx(320.30)
        # Rigetti Cepheus: $0.30 + 4000 * $0.000425
        assert by_device(est, "rigetti_cepheus").usd == pytest.approx(2.00)
        # IQM Garnet: $0.30 + 4000 * $0.00145
        assert by_device(est, "iqm_garnet").usd == pytest.approx(6.10)

    def test_azure_gate_shot_pricing(self):
        est = estimate_circuit(bell(), shots=4000)
        # Aria: $12.4166 min + 4000 * (1 * 0.000220 + 1 * 0.000975)
        assert by_device(est, "ionq_aria").usd == pytest.approx(12.4166 + 4.78)

    def test_quantinuum_reports_credit_units(self):
        est = estimate_circuit(bell(), shots=4000)
        h2 = by_device(est, "quantinuum_h2")
        assert h2.usd is None
        # HQC = 5 + 4000 * (1 + 10*1 + 5*4) / 5000 = 29.8
        assert h2.units == "29.8 HQC"

    def test_ibm_runtime_model(self):
        est = estimate_circuit(bell(), shots=4000)
        ibm = by_device(est, "heron_payg")
        # ~2 seconds (1s overhead + 4000 shots * 250us) at $1.60/s
        assert 2.5 < ibm.usd < 4.5

    def test_sorted_cheapest_first(self):
        est = estimate_circuit(bell(), shots=4000)
        priced = [e.usd for e in est if e.usd is not None and e.feasible]
        assert priced == sorted(priced)

    def test_infeasible_device_flagged_not_priced(self):
        wide = QuantumCircuit(30)
        wide.h(0)
        wide.measure_all()
        est = estimate_circuit(wide, shots=100)
        aqt = by_device(est, "aqt_ibex")  # 12 qubits < 30
        assert not aqt.feasible
        assert aqt.usd is None
        assert "qubit" in aqt.note

    def test_huge_shot_count_price_spread(self):
        # The category-defining fact: identical job, wildly different bills.
        est = estimate_circuit(bell(), shots=200_000)
        ionq = by_device(est, "ionq_forte").usd
        rigetti = by_device(est, "rigetti_cepheus").usd
        assert ionq > 100 * rigetti


class TestSuiteEstimates:
    def test_suite_sums_per_device(self):
        pairs = [(bell(), 1000), (bell(), 3000)]
        suite = estimate_suite(pairs)
        # Rigetti: (0.30 + 1000*0.000425) + (0.30 + 3000*0.000425) = 2.30
        assert by_device(suite, "rigetti_cepheus").usd == pytest.approx(2.30)

    def test_suite_sums_credit_units(self):
        suite = estimate_suite([(bell(), 4000), (bell(), 4000)])
        assert by_device(suite, "quantinuum_h2").units == "59.6 HQC"

    def test_suite_infeasible_if_any_circuit_infeasible(self):
        wide = QuantumCircuit(30)
        wide.h(0)
        wide.measure_all()
        suite = estimate_suite([(bell(), 100), (wide, 100)])
        assert not by_device(suite, "aqt_ibex").feasible


def test_catalog_is_versioned_and_sourced():
    catalog = load_catalog()
    assert catalog["catalog_version"] == 1
    assert catalog["verified"]
    assert catalog["sources"]
