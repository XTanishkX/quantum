# Getting started

## Install

```sh
pip install qontinuum            # core (simulators, cost, everything offline)
pip install 'qontinuum[ibm]'     # + real IBM calibration noise models
pip install 'qontinuum[braket]'  # + AWS Braket hardware submission
```

## Scaffold a project

```sh
qont init --action    # example test, config, .gitignore, PR workflow
qont doctor           # verify the environment is healthy
```

## Write a quantum test

Any file named `q_test_*.py`:

```python
from qiskit import QuantumCircuit
from qontinuum import qtest, assert_distribution

@qtest(shots=4000)
def bell_pair():
    qc = QuantumCircuit(2)
    qc.h(0); qc.cx(0, 1); qc.measure_all()
    return qc

@bell_pair.check
def is_maximally_entangled(result):
    assert_distribution(result, {"00": 0.5, "11": 0.5}, tvd_threshold=0.05)
```

```sh
qont test             # run it
qont lint             # catch statistical footguns before CI does
qont shots plan       # are your shot counts sound for your thresholds?
```

## The daily loop

```sh
qont watch test                      # re-run on every save
qont test --seed 42 --cached         # CI mode: cache unchanged circuits
qont cost                            # what would this cost on real hardware?
qont route --optimize value          # which device should run it?
qont noise headroom bell_pair        # how much calibration drift survives?
```

## Ship it

```sh
qont ci --seed 42                    # markdown report for the PR comment
qont report junit --out junit.xml    # any CI system's native test UI
qont dashboard                       # single-file observability
qont pack create                     # reproducibility bundle for reviewers
```

## Run on real hardware — deliberately

```sh
qont budget set 25 --monthly                       # project-level cap
qont run --on ibm:ibm_brisbane --dry-run           # estimate only
qont run --on braket:rigetti_cepheus --max-cost 5  # all-or-nothing guard
```

Exit codes everywhere: `0` ok · `1` failures/findings · `2` usage or config
error · `3` guard refusal. Every read command takes `--json`.
