"""Execution result passed to check functions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunResult:
    """Measurement outcome of one circuit execution."""

    counts: dict[str, int]
    shots: int
    backend: str
    circuit_hash: str
    seed: int | None = None
    duration_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def probs(self) -> dict[str, float]:
        return {k: v / self.shots for k, v in self.counts.items()}

    def top(self, n: int = 5) -> list[tuple[str, float]]:
        """The n most frequent outcomes with their estimated probabilities."""
        ranked = sorted(self.counts.items(), key=lambda kv: -kv[1])[:n]
        return [(k, v / self.shots) for k, v in ranked]
