"""Sync the outbox to the Quantum Intelligence Network — and stay graceful offline.

``sync`` only does anything when the user has opted in. With no endpoint
configured it is a pure local no-op (records stay queued). With an endpoint it
POSTs the queued records over HTTPS and, on success, clears the outbox and caches
any community snapshot the server returns. **Any** failure — no network, timeout,
non-2xx, bad response — leaves the queue intact and reports the reason; telemetry
never blocks or breaks a workflow.

The network call is injected (``transport``) so the whole flow is testable
without a server, and so the transport layer stays a single, auditable seam.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from qontinuum.telemetry import community, consent, outbox
from qontinuum.telemetry.schema import CommunityAggregate

Transport = Callable[[str, dict, float], dict]


@dataclass
class SyncResult:
    ok: bool
    sent: int
    queued: int
    endpoint: str
    community_updated: bool
    detail: str


def sync(root: Path, *, timeout: float = 10.0, transport: Transport | None = None) -> SyncResult:
    """Attempt to flush the outbox. Safe to call anytime; never raises."""
    queued = outbox.count(root)
    if not consent.is_enabled(root):
        return SyncResult(False, 0, queued, "", False, "telemetry is disabled (opt-in)")

    endpoint = consent.endpoint(root)
    if not endpoint:
        return SyncResult(
            True, 0, queued, "", False,
            f"no endpoint configured; {queued} record(s) kept locally",
        )
    if not endpoint.startswith("https://"):
        return SyncResult(
            False, 0, queued, endpoint, False,
            "endpoint must be https:// — refusing to send over an insecure channel",
        )

    records = outbox.read_all(root)
    if not records:
        return SyncResult(True, 0, 0, endpoint, False, "nothing queued to send")

    payload = {
        "schema": records[0].schema_version,
        "install_id": records[0].install_id,
        "records": [r.model_dump() for r in records],
    }
    send = transport or _http_transport
    try:
        response = send(endpoint.rstrip("/") + "/contribute", payload, timeout)
    except Exception as exc:  # graceful offline: keep the queue, report why
        return SyncResult(False, 0, queued, endpoint, False, f"offline / unreachable: {exc}")

    updated = _maybe_cache_community(root, response)
    dropped = outbox.clear(root)
    return SyncResult(
        True, dropped, 0, endpoint, updated,
        f"sent {dropped} record(s)" + (" · community snapshot updated" if updated else ""),
    )


def pull_community(
    root: Path, *, timeout: float = 10.0, transport: Transport | None = None
) -> bool:
    """Fetch and cache the latest community snapshot. Returns True if updated."""
    endpoint = consent.endpoint(root)
    if not endpoint or not endpoint.startswith("https://"):
        return False
    send = transport or _http_transport
    try:
        response = send(endpoint.rstrip("/") + "/community", {}, timeout)
    except Exception:
        return False
    return _maybe_cache_community(root, response)


def _maybe_cache_community(root: Path, response: object) -> bool:
    if not isinstance(response, dict):
        return False
    raw = response.get("community")
    if not isinstance(raw, dict):
        return False
    try:
        aggregate = CommunityAggregate.model_validate(raw)
    except ValueError:
        return False
    if not aggregate.is_compatible():
        return False
    community.save(root, aggregate)
    return True


def _http_transport(url: str, payload: dict, timeout: float) -> dict:
    """POST JSON over HTTPS and parse a JSON response. The only network seam."""
    if not url.startswith("https://"):  # defence in depth
        raise ValueError("refusing non-HTTPS telemetry endpoint")
    data = json.dumps(payload).encode()
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "qontinuum-telemetry"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        body = resp.read().decode()
    return json.loads(body) if body else {}
