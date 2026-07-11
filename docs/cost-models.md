# How Qontinuum prices a circuit

Provider pricing is structurally heterogeneous — that's exactly why a comparison table
is valuable. The catalog (`src/qontinuum/cost/catalog.yaml`) records each device under
one of four pricing *models*; the estimator only implements the models, never
device-specific code.

## Models

**`per_shot` (AWS Braket QPUs)**
`cost = per_task + shots × per_shot`. Braket charges $0.30 per task plus a per-shot
rate that spans two orders of magnitude across vendors (Rigetti $0.000425 vs IonQ
$0.08 per shot).

**`per_second` (IBM Quantum Pay-As-You-Go)**
IBM bills QPU seconds ($1.60/s). Runtime is estimated with a parametric model:

```
seconds = overhead + shots × (per_shot_delay + depth × per_layer_time)
```

The default repetition delay (~250 µs) dominates: 4,000 shots ≈ 1 s of QPU time plus
setup overhead. This is deliberately labeled an *estimate* — actual runtime depends on
transpilation and device configuration.

**`gate_shot` (Azure Quantum, IonQ devices)**
Azure bills IonQ by gate-shots: `min_program + shots × (N1q·rate1q + N2q·rate2q)`.
Multi-controlled gates are billed as `6×(N−2)` two-qubit gates, which the circuit
profiler applies. Error-mitigation defaults matter enormously: leaving it on raises the
Aria minimum from $12.42 to $97.50 per program.

**`hqc` (Quantinuum)**
Quantinuum bills in H-System Quantum Credits:
`HQC = 5 + shots × (N1q + 10·N2q + 5·Nm) / 5000`, where `Nm` counts state prep and
measurement. The PAYG dollar rate is not public, so Qontinuum reports the HQC quantity
rather than inventing a dollar figure.

## Honesty rules

- Every catalog entry carries the date its price was verified and source URLs.
- Estimates use the circuit *as written*; providers bill the compiled form, which can
  differ after transpilation to native gates.
- Devices that can't fit the circuit (qubit count) are shown as infeasible, not priced.
- Output is always labeled "estimates, not quotes."
