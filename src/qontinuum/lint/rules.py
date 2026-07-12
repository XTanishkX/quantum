"""Lint rules Q001-Q009 — the quantum-test footguns we keep seeing.

Each rule gets a :class:`LintContext` for one discovered test and yields
:class:`Finding`s. Rules must stay cheap: one bounded ideal simulation per
test is allowed (shared via the context), nothing slower.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qontinuum.assertions.stats import sampling_floor


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # "error" | "warning"
    test_id: str
    message: str


@dataclass
class LintContext:
    test_id: str
    test: Any  # QuantumTest
    circuit: Any | None  # QuantumCircuit or None when build() failed
    build_error: str | None
    events: list[Any] = field(default_factory=list)  # AssertionEvents from a probe run
    has_snapshot_baseline: bool = False


RULES: dict[str, tuple[str, str, str]] = {
    # code: (severity, title, explanation)
    "Q001": ("error", "threshold below sampling floor",
             "The assertion threshold is smaller than what the configured shot count can "
             "statistically resolve — a perfect device would still fail sometimes. Raise "
             "shots (see `qont shots for-tvd`) or loosen the threshold."),
    "Q002": ("error", "circuit has no measurements",
             "The test circuit never measures, so it produces no counts and every check "
             "operates on nothing. Add `circuit.measure_all()` or explicit measures."),
    "Q003": ("warning", "idle qubits",
             "Qubits are allocated but never touched by any operation. Usually a leftover "
             "from refactoring; they widen the state space and slow simulation for free."),
    "Q004": ("error", "unbound circuit parameters",
             "The circuit still contains free `Parameter`s at execution time, which will "
             "fail at run. Bind them in the factory (e.g. `circuit.assign_parameters`)."),
    "Q005": ("warning", "very deep circuit on a noisy backend",
             "Depth beyond a few hundred layers on a NISQ noise model usually decoheres "
             "into noise — the test may only be asserting 'noise looks like noise'."),
    "Q006": ("error", "snapshot test without a committed baseline",
             "snapshot=True but no baseline exists in .qontinuum/snapshots.json — the test "
             "will error in CI. Run `qont snapshot update` and commit the file."),
    "Q007": ("warning", "many statistical checks on one sample",
             "Four or more checks share a single run's counts; at 99% soundness each, the "
             "suite-level false-failure rate compounds. Raise shots or consolidate checks."),
    "Q008": ("warning", "live-calibration backend in the test path",
             "backend='...@live' fetches calibration over the network at test time — CI "
             "becomes network- and account-dependent. Use the bundled snapshot form "
             "('ibm:<device>') in tests; reserve @live for scheduled jobs."),
    "Q009": ("warning", "trivially low shot count",
             "Fewer than 100 shots cannot support any statistical assertion beyond "
             "smoke-testing. Raise shots or drop the checks."),
}

_DEEP_CIRCUIT_DEPTH = 300


def run_rules(ctx: LintContext) -> list[Finding]:
    findings: list[Finding] = []

    def add(code: str, message: str) -> None:
        findings.append(Finding(code, RULES[code][0], ctx.test_id, message))

    # Build-time problems: report what we can, then stop for this test.
    if ctx.build_error is not None:
        if "measure" in ctx.build_error:
            add("Q002", ctx.build_error)
        elif "parameter" in ctx.build_error.lower():
            add("Q004", ctx.build_error)
        if ctx.test.snapshot and not ctx.has_snapshot_baseline:
            add("Q006", "run `qont snapshot update` and commit .qontinuum/snapshots.json")
        return findings
    circuit = ctx.circuit

    if circuit.num_clbits == 0:
        add("Q002", "no classical bits / measurements in the built circuit")
    if getattr(circuit, "parameters", None):
        add("Q004", f"unbound parameters: {sorted(p.name for p in circuit.parameters)}")

    # Usage means gates — a qubit that is only measured/reset was never used.
    passive = {"measure", "barrier", "reset", "delay"}
    used = {
        q for instr in circuit.data if instr.operation.name not in passive
        for q in instr.qubits
    }
    idle = circuit.num_qubits - len({circuit.find_bit(q).index for q in used})
    if idle > 0:
        add("Q003", f"{idle} of {circuit.num_qubits} qubits are never gated")

    if ctx.test.backend != "aer" and circuit.depth() > _DEEP_CIRCUIT_DEPTH:
        add("Q005", f"depth {circuit.depth()} on backend {ctx.test.backend!r}")

    if "@live" in ctx.test.backend:
        add("Q008", f"backend {ctx.test.backend!r} needs network + account at test time")

    if ctx.test.shots < 100:
        add("Q009", f"shots={ctx.test.shots}")

    # Q001 — thresholds vs the floor, from the probe run's captured events
    for event in ctx.events:
        if event.threshold is None:
            continue
        if event.kind == "tvd":
            floor = sampling_floor(2, ctx.test.shots)  # k=2 lower-bounds every support
            if event.threshold < floor:
                add("Q001",
                    f"tvd_threshold={event.threshold} < floor {floor:.4f} "
                    f"at {ctx.test.shots} shots (even for 2 outcomes)")

    if ctx.test.snapshot and not ctx.has_snapshot_baseline:
        add("Q006", "run `qont snapshot update` and commit .qontinuum/snapshots.json")

    if len(ctx.test.checks) >= 4:
        add("Q007", f"{len(ctx.test.checks)} checks share one sample")

    return findings
