"""PursuitModule Protocol and BaseModule convenience class.

@decision DEC-MODULE-001
@title async def hunt() from day 1
@status accepted
@rationale Prevents expensive refactor when the asyncio event bus arrives in
           Phase 4 (Issue #19). httpx.AsyncClient is the planned HTTP library.
           cmd2 handlers call asyncio.run() to bridge sync->async.

@decision DEC-MODULE-002
@title Protocol over ABC for module contract
@status accepted
@rationale @runtime_checkable Protocol allows isinstance() checks without
           requiring inheritance. Third-party module authors can implement the
           protocol with any class hierarchy — they are not forced to inherit
           from BaseModule. BaseModule is provided purely as a convenience for
           common patterns, not as a mandatory base class.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PursuitModule(Protocol):
    """Contract for all AP modules (built-in and third-party).

    Third-party modules register via entry_points(group="adversary_pursuit.modules").
    They must satisfy this Protocol — inheritance from BaseModule is optional.

    Attributes
    ----------
    name:        Canonical path, e.g. "osint/whois_lookup"
    description: One-line human-readable description
    author:      Author name or team
    module_type: One of "osint", "cti", "pivoting"
    options:     Parameter definitions; each value is a dict with keys:
                 required (bool), description (str), default (Any)
    """

    name: str
    description: str
    author: str
    module_type: str
    options: dict[str, Any]

    def initialize(self, config: dict[str, Any]) -> None:
        """Configure with API keys and settings. No side effects outside self."""
        ...

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Execute query and return STIX 2.1 observables as plain dicts.

        Each dict represents a STIX 2.1 SCO (Cyber Observable).
        Full python-stix2 object wrapping comes in Issue #4.

        Parameters
        ----------
        target:
            The primary observable to investigate (IP, domain, hash, etc.)
        options:
            Runtime options that override module defaults. Keys match the
            option names defined in self.options.

        Returns
        -------
        list[dict]
            List of STIX-like dicts. At minimum each dict has:
            - "type": STIX SCO type string (e.g. "ipv4-addr", "domain-name")
            - "value": the observable value
        """
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ModuleError(Exception):
    """Base exception for module-level errors (rate limit, auth, network)."""


class AuthenticationError(ModuleError):
    """API key missing or invalid.

    Raised when a module cannot authenticate with its upstream service.
    The caller should check config.get_api_key() before running the module.
    """


class RateLimitError(ModuleError):
    """API rate limit exceeded.

    Parameters
    ----------
    message:     Human-readable explanation
    retry_after: Seconds until the rate limit resets, if known by the API
    """

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# BaseModule
# ---------------------------------------------------------------------------


class BaseModule:
    """Convenience base class implementing common PursuitModule patterns.

    Modules CAN extend this for shared behavior but are not required to —
    the Protocol is the contract, not inheritance.  See DEC-MODULE-002.

    Subclasses must override the class-level attributes and implement hunt().

    Example
    -------
    class MyModule(BaseModule):
        name = "osint/my_lookup"
        description = "Look up things"
        author = "me"
        module_type = "osint"

        async def hunt(self, target, options):
            return [{"type": "domain-name", "value": target}]
    """

    name: str = ""
    description: str = ""
    author: str = ""
    module_type: str = ""
    accepts: tuple = ()

    def __init__(self) -> None:
        self.options: dict[str, Any] = {}
        self._config: dict[str, Any] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        """Store config dict (API keys, timeouts, etc.) for use in hunt()."""
        self._config = config

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        """Raise NotImplementedError — subclasses must override."""
        raise NotImplementedError(f"{self.name or type(self).__name__} must implement hunt()")
