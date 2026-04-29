"""Plugin discovery and management via importlib.metadata entry points.

@decision DEC-PLUGIN-001
@title entry_points + direct registration; built-ins registered in load_plugins()
@status accepted
@rationale importlib.metadata entry_points(group="adversary_pursuit.modules")
           is the standard packaging mechanism for plugin systems. However,
           entry_points only work after a package is installed (pip install -e .).
           To support both development (editable install) and testing without
           installation, PluginManager.load_plugins() also calls
           register_module() directly for built-in modules. This ensures the
           two no-API-key built-ins are always available regardless of install
           state. Third-party plugins register only via entry_points.

@decision DEC-PLUGIN-002
@title Failed module loads are logged, not raised
@status accepted
@rationale A broken third-party plugin must not prevent AP from starting.
           get_module() catches instantiation errors, logs them, and returns
           None. This matches the Metasploit model where a broken module is
           skipped rather than crashing the framework. The caller can check
           for None and present a user-friendly error.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any

from adversary_pursuit.modules.base import PursuitModule

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Built-in module registration
# ---------------------------------------------------------------------------

# Imported lazily inside load_plugins() to avoid circular imports and to
# make the registration location explicit and auditable.

_BUILTIN_MODULES: list[tuple[str, str]] = [
    ("osint/whois_lookup", "adversary_pursuit.modules.osint.whois_lookup:WhoisLookup"),
    ("osint/dns_resolve", "adversary_pursuit.modules.osint.dns_resolve:DnsResolve"),
    ("osint/abuseipdb", "adversary_pursuit.modules.osint.abuseipdb:AbuseIPDB"),
    ("osint/urlscan", "adversary_pursuit.modules.osint.urlscan:URLScan"),
    ("osint/hibp", "adversary_pursuit.modules.osint.hibp:HIBP"),
    ("osint/shodan_ip", "adversary_pursuit.modules.osint.shodan_ip:ShodanIP"),
    ("osint/censys_host", "adversary_pursuit.modules.osint.censys_host:CensysHost"),
    ("cti/virustotal", "adversary_pursuit.modules.cti.virustotal:VirusTotal"),
    ("cti/otx", "adversary_pursuit.modules.cti.otx:AlienVaultOTX"),
]


def _import_class(dotted: str) -> type:
    """Import a class from a 'module.path:ClassName' string."""
    module_path, class_name = dotted.split(":", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


# ---------------------------------------------------------------------------
# PluginManager
# ---------------------------------------------------------------------------

class PluginManager:
    """Discovers and manages PursuitModule implementations.

    Discovery order (both sources merged into _modules dict):
    1. Built-in modules registered directly in load_plugins()
    2. Third-party modules via importlib.metadata entry_points

    Failed loads (import errors, bad class definitions) are logged but do
    not crash the manager. See DEC-PLUGIN-002.

    Usage
    -----
    pm = PluginManager()
    pm.load_plugins()
    mod = pm.get_module("osint/whois_lookup")
    mod.initialize(config)
    results = await mod.hunt("example.com", {})
    """

    def __init__(self) -> None:
        # Maps canonical path -> module class (not instance)
        # e.g. "osint/whois_lookup" -> WhoisLookup
        self._modules: dict[str, type] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_plugins(self) -> None:
        """Discover and load all registered modules.

        Loads built-in modules first, then scans entry_points for
        third-party plugins. Each source is loaded independently so a
        failure in one entry point does not block others.
        """
        # 1. Register built-ins directly (always available)
        for path, dotted in _BUILTIN_MODULES:
            try:
                cls = _import_class(dotted)
                self.register_module(path, cls)
                logger.debug("Loaded built-in module: %s", path)
            except Exception as exc:
                logger.error("Failed to load built-in module %s: %s", path, exc)

        # 2. Scan entry_points for third-party plugins
        try:
            eps = entry_points(group="adversary_pursuit.modules")
        except Exception as exc:
            logger.warning("Could not read entry_points: %s", exc)
            return

        for ep in eps:
            try:
                cls = ep.load()
                # Use the module's self-declared name if available,
                # falling back to the entry point name
                path = getattr(cls, "name", ep.name)
                self.register_module(path, cls)
                logger.debug("Loaded plugin module: %s (entry point: %s)", path, ep.name)
            except Exception as exc:
                logger.error("Failed to load plugin %s: %s", ep.name, exc)

    def register_module(self, path: str, module_class: type) -> None:
        """Manually register a module class by path.

        Parameters
        ----------
        path:
            Canonical path, e.g. "osint/whois_lookup"
        module_class:
            A class (not instance) implementing PursuitModule
        """
        self._modules[path] = module_class

    def get_module(self, path: str) -> PursuitModule | None:
        """Return an instantiated module by canonical path.

        Parameters
        ----------
        path:
            e.g. "osint/whois_lookup"

        Returns
        -------
        PursuitModule instance, or None if path is unknown or instantiation
        fails (see DEC-PLUGIN-002).
        """
        cls = self._modules.get(path)
        if cls is None:
            return None
        try:
            return cls()
        except Exception as exc:
            logger.error("Failed to instantiate module %s: %s", path, exc)
            return None

    def search(self, keyword: str) -> list[dict[str, Any]]:
        """Search modules by name, description, or module_type.

        Parameters
        ----------
        keyword:
            Case-insensitive search term matched against name, description,
            and module_type fields.

        Returns
        -------
        list of dicts with keys: name, description, type
        """
        kw = keyword.lower()
        results = []
        for path, cls in self._modules.items():
            name = getattr(cls, "name", path)
            description = getattr(cls, "description", "")
            module_type = getattr(cls, "module_type", "")
            if (
                kw in name.lower()
                or kw in description.lower()
                or kw in module_type.lower()
            ):
                results.append({
                    "name": name,
                    "description": description,
                    "type": module_type,
                })
        return results

    def list_modules(self) -> list[dict[str, Any]]:
        """Return metadata for all loaded modules.

        Returns
        -------
        list of dicts with keys: name, description, type, author
        """
        modules = []
        for path, cls in self._modules.items():
            modules.append({
                "name": getattr(cls, "name", path),
                "description": getattr(cls, "description", ""),
                "type": getattr(cls, "module_type", ""),
                "author": getattr(cls, "author", ""),
            })
        return modules
