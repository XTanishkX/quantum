# Backends

Backend specs are strings so test files stay declarative and CI-safe.

| Spec | What runs | Needs |
|---|---|---|
| `aer` (default) | Ideal (noiseless) local simulation via Qiskit Aer | nothing |
| `ibm:<device>` | Local Aer simulation under the named IBM device's bundled calibration snapshot (real historical noise data: gate errors, readout errors, T1/T2) | `pip install 'qontinuum[ibm]'` |
| `ibm:<device>@live` | Same, but with the device's *current* calibration fetched at run time | a saved (free) IBM Quantum account |

```python
@qtest(shots=4000)                          # ideal
def bell(): ...

@qtest(shots=4000, backend="ibm:manila")    # offline, real noise profile
def bell_noisy(): ...

@qtest(shots=4000, backend="ibm:brisbane@live")  # today's calibration
def bell_today(): ...
```

Device names are matched leniently: `manila`, `fake_manila`, and `ibm_manila` all
resolve to the same snapshot. Unknown names fail with the list of available devices.

## Setting thresholds under noise

Ideal-simulator thresholds (e.g. `tvd_threshold=0.05`) are usually too strict under a
real noise model. A practical workflow:

1. Run once with `qont test` against the noisy backend and look at the reported TVD.
2. Set the threshold with headroom above the observed value but below "broken"
   (a missing gate typically moves TVD by 0.3+, an order of magnitude above noise).
3. Or use `snapshot=True` and let the two-sample test track the noisy distribution
   itself — then calibration-snapshot updates are reviewed like any other diff.

## Why simulate noise instead of running on hardware?

CI needs to be fast, free, and deterministic-ish. Real-hardware execution (queues,
cost, calibration drift) belongs in scheduled/gated jobs, not on every push — that's
what `qont run --on <provider:device> --max-cost <usd>` is for: the whole suite is
priced up front and nothing is submitted unless the estimate clears the budget
(default $0). Noise-model simulation from real calibration data catches the class of
bugs unit tests can: logic regressions, and "this circuit is now too deep to survive
realistic noise."
