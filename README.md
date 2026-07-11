# Qontinuum

**CI/CD, noise-aware regression testing, and cost intelligence for quantum programs.**

Quantum programs don't return values — they return probability distributions sampled from
noisy hardware. `assert result == expected` doesn't work, and nothing in the classical CI
toolchain knows that. Qontinuum does:

- **`qont test`** — a pytest-style runner for quantum circuits with *statistical* assertions:
  total variation distance with shots-aware confidence bounds, chi-squared tests, fidelity
  thresholds, and snapshot baselines committed as JSON.
- **`qont cost`** — estimates what your test suite would cost on real hardware, across
  providers (IonQ, Rigetti, IQM via Braket; IBM; Azure Quantum), before you spend a cent.
- **`qont ci`** — one command for CI: run the suite, render a markdown report.
- **GitHub Action** — posts a sticky PR comment: regression pass/fail plus
  *"running this suite on hardware: IonQ $42.10 / Rigetti $0.90 / IBM ~$3.20."*
- **Noise-aware testing** — build Aer noise models from real IBM device calibration data,
  so CI tests against *today's* hardware noise, for free.

> Status: pre-release (v0.1 in development).

## Install

```sh
pip install qontinuum
```

## Quick start

```python
# q_test_bell.py
from qiskit import QuantumCircuit
from qontinuum import qtest, assert_distribution

@qtest(shots=4000)
def bell_pair():
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc

@bell_pair.check
def is_maximally_entangled(result):
    assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.05)
```

```sh
$ qont test
✓ bell_pair::is_maximally_entangled   TVD 0.011 < 0.05   (4000 shots, aer ideal)
```

## License

Apache-2.0
