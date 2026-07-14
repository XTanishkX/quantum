"""Discover and resolve plugins from built-ins plus installed entry points.

Discovery is a hybrid on purpose:

- **Built-ins** (:func:`qontinuum.plugins.builtins.builtin_plugins`) are the
  source of truth and are always present, independent of install metadata.
- **Entry points** in the ``qontinuum.{providers,backends,sdks}`` groups add
  third-party plugins. Each is loaded in isolation: a broken or misdeclared
  plugin becomes an unavailable :class:`~qontinuum.plugins.base.PluginRecord`
  carrying its error, and never breaks discovery or the CLI.

A third-party plugin whose name collides with a built-in *shadows* it (the
entry point wins), which is recorded so ``qont plugin list`` can surface it.
Results are cached per process; call :meth:`PluginRegistry.refresh` to rebuild.
"""

from __future__ import annotations

from importlib import metadata
from typing import Any

from qontinuum.plugins.base import (
    ENTRY_POINT_GROUPS,
    PluginError,
    PluginRecord,
)
from qontinuum.plugins.builtins import builtin_plugins


class PluginRegistry:
    """Lazily-built, cached view of every discoverable plugin."""

    def __init__(self) -> None:
        self._records: dict[str, dict[str, PluginRecord]] | None = None

    # -- discovery ---------------------------------------------------------- #
    def refresh(self) -> None:
        """Drop the cache so the next access rediscovers plugins."""
        self._records = None

    def _ensure(self) -> dict[str, dict[str, PluginRecord]]:
        if self._records is None:
            self._records = self._discover()
        return self._records

    def _discover(self) -> dict[str, dict[str, PluginRecord]]:
        by_kind: dict[str, dict[str, PluginRecord]] = {k: {} for k in ENTRY_POINT_GROUPS}
        for kind, plugins in builtin_plugins().items():
            for plugin in plugins:
                rec = _record_from_plugin(plugin, kind=kind, source="builtin")
                by_kind[kind][rec.name] = rec
        for kind, group in ENTRY_POINT_GROUPS.items():
            for ep in _iter_entry_points(group):
                rec = _record_from_entry_point(ep, kind=kind)
                prior = by_kind[kind].get(rec.name)
                if prior is not None:
                    rec = _with_shadow(rec, prior.source)
                by_kind[kind][rec.name] = rec
        return by_kind

    # -- queries ------------------------------------------------------------ #
    def records(self) -> list[PluginRecord]:
        """Every discovered plugin, ordered by kind then name."""
        out: list[PluginRecord] = []
        for kind in ENTRY_POINT_GROUPS:
            out.extend(r for _, r in sorted(self._ensure()[kind].items()))
        return out

    def records_for(self, kind: str) -> list[PluginRecord]:
        return [r for _, r in sorted(self._ensure()[kind].items())]

    def get(self, kind: str, name: str) -> PluginRecord | None:
        return self._ensure()[kind].get(name)

    def names(self, kind: str) -> list[str]:
        return sorted(self._ensure()[kind])

    def available(self, kind: str) -> list[Any]:
        """The loaded plugin objects for one kind (skips unavailable ones)."""
        return [r.plugin for r in self.records_for(kind) if r.available]

    def require(self, kind: str, name: str) -> Any:
        """Return a loaded plugin object or raise :class:`PluginError`."""
        rec = self.get(kind, name)
        if rec is None:
            known = ", ".join(self.names(kind)) or "none"
            raise PluginError(f"no {kind} plugin named {name!r} (known: {known})")
        if not rec.available:
            raise PluginError(f"{kind} plugin {name!r} failed to load: {rec.error}")
        return rec.plugin


# --------------------------------------------------------------------------- #
# Record construction helpers
# --------------------------------------------------------------------------- #
def _record_from_plugin(
    plugin: Any, *, kind: str, source: str, dist: str | None = None
) -> PluginRecord:
    return PluginRecord(
        name=str(getattr(plugin, "name", type(plugin).__name__)),
        kind=kind,
        source=source,
        available=True,
        summary=str(getattr(plugin, "summary", "")),
        requires=tuple(getattr(plugin, "requires", ()) or ()),
        extra=getattr(plugin, "extra", None),
        dist=dist,
        plugin=plugin,
    )


def _record_from_entry_point(ep: metadata.EntryPoint, *, kind: str) -> PluginRecord:
    dist = _dist_name(ep)
    try:
        obj = ep.load()
        if isinstance(obj, type):
            obj = obj()
    except Exception as exc:
        return PluginRecord(
            name=ep.name,
            kind=kind,
            source="entrypoint",
            available=False,
            dist=dist,
            error=f"{type(exc).__name__}: {exc}",
        )
    return _record_from_plugin(obj, kind=kind, source="entrypoint", dist=dist)


def _with_shadow(rec: PluginRecord, shadowed_source: str) -> PluginRecord:
    from dataclasses import replace

    return replace(rec, shadows=shadowed_source)


def _iter_entry_points(group: str) -> list[metadata.EntryPoint]:
    try:
        return list(metadata.entry_points(group=group))
    except Exception:  # pragma: no cover - defensive; metadata should not raise
        return []


def _dist_name(ep: metadata.EntryPoint) -> str | None:
    dist = getattr(ep, "dist", None)
    if dist is None:
        return None
    name = getattr(dist, "name", None)
    return str(name) if name else None


# --------------------------------------------------------------------------- #
# Process-wide singleton + convenience API
# --------------------------------------------------------------------------- #
_REGISTRY = PluginRegistry()


def get_registry() -> PluginRegistry:
    """The shared, process-wide plugin registry."""
    return _REGISTRY
