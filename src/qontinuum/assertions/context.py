"""Capture assertion statistics even when checks pass.

Assertions call :func:`record` with the statistic they computed; the runner
wraps each check in :func:`capture_assertions` so passing runs still carry
their TVD/fidelity/p-value into reports and the dashboard trend charts.
Outside a capture context, :func:`record` is a no-op, so assertions behave
normally when called directly (e.g. inside pytest).
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class AssertionEvent:
    kind: str  # e.g. "tvd", "fidelity", "chi2_pvalue"
    statistic: float
    threshold: float | None


_events: ContextVar[list[AssertionEvent] | None] = ContextVar(
    "qontinuum_assertion_events", default=None
)


@contextmanager
def capture_assertions():
    """Collect AssertionEvents emitted by assertions run inside this context."""
    events: list[AssertionEvent] = []
    token = _events.set(events)
    try:
        yield events
    finally:
        _events.reset(token)


def record(kind: str, statistic: float, threshold: float | None = None) -> None:
    events = _events.get()
    if events is not None:
        events.append(AssertionEvent(kind, float(statistic), threshold))
