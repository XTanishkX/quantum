"""Local cache of the community-intelligence snapshot.

A :class:`CommunityAggregate` is per-device counts and averages only — never raw
records — so it is safe to distribute and cache. It is stored under
.qontinuum/telemetry/community.json and validated (schema + shape) on every load;
an incompatible or corrupt cache is ignored rather than trusted, so a bad
download can never poison recommendations.
"""

from __future__ import annotations

import json
from pathlib import Path

from qontinuum.telemetry.outbox import telemetry_dir
from qontinuum.telemetry.schema import CommunityAggregate

COMMUNITY_FILE = "community.json"


def community_path(root: Path) -> Path:
    return telemetry_dir(root) / COMMUNITY_FILE


def load(root: Path) -> CommunityAggregate | None:
    """Return the cached community snapshot, or ``None`` if absent/invalid."""
    path = community_path(root)
    if not path.is_file():
        return None
    try:
        aggregate = CommunityAggregate.model_validate_json(path.read_text())
    except ValueError:
        return None
    if not aggregate.is_compatible():
        return None
    return aggregate


def save(root: Path, aggregate: CommunityAggregate) -> Path:
    """Validate and cache a community snapshot; raises on incompatible schema."""
    if not aggregate.is_compatible():
        raise ValueError(
            f"community snapshot schema {aggregate.schema_version} is not supported"
        )
    path = community_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(aggregate.model_dump(), indent=2))
    return path
