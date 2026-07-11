"""The @qtest decorator: declare a circuit as a quantum test."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qiskit import QuantumCircuit

from qontinuum.runner.result import RunResult

CheckFn = Callable[[RunResult], Any]


class QuantumTest:
    """A circuit factory plus the statistical checks to run against its output."""

    def __init__(
        self,
        factory: Callable[[], QuantumCircuit],
        *,
        shots: int = 1024,
        backend: str = "aer",
        snapshot: bool = False,
        name: str | None = None,
    ):
        self.factory = factory
        self.name = name or factory.__name__
        self.shots = shots
        self.backend = backend
        self.snapshot = snapshot
        self.checks: list[CheckFn] = []
        self.__doc__ = factory.__doc__

    def check(self, fn: CheckFn) -> CheckFn:
        """Register a check; the function receives the RunResult."""
        self.checks.append(fn)
        return fn

    def build(self) -> QuantumCircuit:
        circuit = self.factory()
        if not isinstance(circuit, QuantumCircuit):
            raise TypeError(
                f"quantum test {self.name!r} must return a QuantumCircuit, "
                f"got {type(circuit).__name__}"
            )
        if circuit.num_clbits == 0:
            raise ValueError(
                f"quantum test {self.name!r} has no measurements; "
                f"add measure instructions (e.g. circuit.measure_all())"
            )
        return circuit

    def __repr__(self) -> str:  # pragma: no cover
        return f"QuantumTest({self.name!r}, shots={self.shots}, backend={self.backend!r})"


def qtest(
    fn: Callable[[], QuantumCircuit] | None = None,
    *,
    shots: int = 1024,
    backend: str = "aer",
    snapshot: bool = False,
    name: str | None = None,
) -> Any:
    """Mark a zero-argument circuit factory as a quantum test.

    Usable bare (``@qtest``) or configured (``@qtest(shots=4000)``). Attach
    statistical checks with ``@<test>.check``; enable ``snapshot=True`` to
    compare each run against a committed golden baseline.
    """

    def wrap(factory: Callable[[], QuantumCircuit]) -> QuantumTest:
        return QuantumTest(
            factory, shots=shots, backend=backend, snapshot=snapshot, name=name
        )

    return wrap(fn) if fn is not None else wrap
