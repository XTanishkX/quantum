"""The Qontinuum plugin system: providers, backends, and SDK adapters.

Public API::

    from qontinuum.plugins import get_registry

    reg = get_registry()
    reg.records()                 # every discovered plugin
    reg.require("provider", "ibm")  # a loaded plugin, or PluginError

See :mod:`qontinuum.plugins.base` for the plugin protocols and
``docs/plugins.md`` for the authoring guide.
"""

from qontinuum.plugins.base import (
    ENTRY_POINT_GROUPS,
    BackendPlugin,
    PluginError,
    PluginRecord,
    ProviderPlugin,
    SDKPlugin,
)
from qontinuum.plugins.registry import PluginRegistry, get_registry

__all__ = [
    "ENTRY_POINT_GROUPS",
    "BackendPlugin",
    "PluginError",
    "PluginRecord",
    "PluginRegistry",
    "ProviderPlugin",
    "SDKPlugin",
    "get_registry",
]
