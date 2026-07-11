"""Versioned, provider-agnostic result schema.

This JSON schema is the contract between the runner, the GitHub Action, and
any future dashboard — bump ``SCHEMA_VERSION`` on breaking changes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class CheckResult(BaseModel):
    name: str
    status: Status
    message: str = ""
    statistic: float | None = None
    threshold: float | None = None


class TestResult(BaseModel):
    id: str
    status: Status
    backend: str = ""
    shots: int = 0
    circuit_hash: str = ""
    counts: dict[str, int] = Field(default_factory=dict)
    checks: list[CheckResult] = Field(default_factory=list)
    duration_ms: float = 0.0
    error: str = ""


class SuiteResult(BaseModel):
    schema_version: int = SCHEMA_VERSION
    tool_version: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    seed: int | None = None
    tests: list[TestResult] = Field(default_factory=list)

    @property
    def status(self) -> Status:
        statuses = {t.status for t in self.tests}
        if Status.ERROR in statuses:
            return Status.ERROR
        if Status.FAIL in statuses:
            return Status.FAIL
        return Status.PASS

    def tally(self) -> dict[str, int]:
        tally = {s.value: 0 for s in Status}
        for t in self.tests:
            tally[t.status.value] += 1
        return tally
