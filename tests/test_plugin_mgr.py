"""Tests for the plugin discovery and module system (Issue #3).

Tests cover:
- PursuitModule Protocol (runtime_checkable)
- BaseModule convenience class
- ModuleError hierarchy
- PluginManager discovery and registration
- Built-in module hunt() execution against real external services

Production sequence note: In production, PluginManager.load_plugins() is
called at app startup, then get_module() / search() are called per user
command. Tests exercise this full sequence including mixed states.

@decision DEC-TEST-MODULE-001
@title Test built-in modules with real network calls (no mocks)
@status accepted
@rationale Per Sacred Practice #5, tests run against real implementations.
           WhoisLookup and DnsResolve use stdlib (socket, subprocess) with
           no external API keys — network calls to example.com are acceptable
           test fixtures. Mocking socket.getaddrinfo would only prove the
           mock, not the module behavior.
"""

import asyncio
import pytest

from adversary_pursuit.modules.base import (
    PursuitModule,
    BaseModule,
    ModuleError,
    AuthenticationError,
    RateLimitError,
)
from adversary_pursuit.core.plugin_mgr import PluginManager
from adversary_pursuit.modules.osint.whois_lookup import WhoisLookup
from adversary_pursuit.modules.osint.dns_resolve import DnsResolve


# ---------------------------------------------------------------------------
# Protocol / base class tests
# ---------------------------------------------------------------------------

class TestPursuitModuleProtocol:
    """Verify the Protocol contract is runtime-checkable and well-defined."""

    def test_whois_satisfies_protocol(self):
        """WhoisLookup must satisfy PursuitModule isinstance check."""
        module = WhoisLookup()
        assert isinstance(module, PursuitModule)

    def test_dns_satisfies_protocol(self):
        """DnsResolve must satisfy PursuitModule isinstance check."""
        module = DnsResolve()
        assert isinstance(module, PursuitModule)

    def test_base_module_has_required_attributes(self):
        """BaseModule subclass with fields set satisfies PursuitModule."""

        class ConcreteModule(BaseModule):
            name = "test/module"
            description = "A test module"
            author = "test"
            module_type = "osint"

            async def hunt(self, target, options):
                return []

        mod = ConcreteModule()
        assert isinstance(mod, PursuitModule)

    def test_initialize_sets_config(self):
        """initialize() stores config for use during hunt()."""
        module = WhoisLookup()
        module.initialize({"api_key": "test-key", "timeout": 30})
        assert module._config == {"api_key": "test-key", "timeout": 30}

    def test_base_module_hunt_raises_not_implemented(self):
        """Base class hunt() must raise NotImplementedError."""

        class EmptyModule(BaseModule):
            name = "empty"

        mod = EmptyModule()
        with pytest.raises(NotImplementedError):
            asyncio.run(mod.hunt("target", {}))


# ---------------------------------------------------------------------------
# Exception hierarchy tests
# ---------------------------------------------------------------------------

class TestModuleErrorHierarchy:
    """ModuleError, AuthenticationError, and RateLimitError hierarchy."""

    def test_authentication_error_is_module_error(self):
        err = AuthenticationError("bad key")
        assert isinstance(err, ModuleError)
        assert isinstance(err, Exception)

    def test_rate_limit_error_is_module_error(self):
        err = RateLimitError("too fast", retry_after=60)
        assert isinstance(err, ModuleError)

    def test_rate_limit_error_stores_retry_after(self):
        err = RateLimitError("slow down", retry_after=120)
        assert err.retry_after == 120

    def test_rate_limit_error_retry_after_optional(self):
        err = RateLimitError("slow down")
        assert err.retry_after is None

    def test_module_error_message(self):
        err = ModuleError("something went wrong")
        assert str(err) == "something went wrong"


# ---------------------------------------------------------------------------
# PluginManager tests
# ---------------------------------------------------------------------------

class TestPluginManager:
    """Full PluginManager lifecycle: load, get, search, list."""

    def test_load_plugins_discovers_builtin_modules(self):
        """load_plugins() must register whois_lookup and dns_resolve."""
        pm = PluginManager()
        pm.load_plugins()
        modules = pm.list_modules()
        names = [m["name"] for m in modules]
        assert "osint/whois_lookup" in names
        assert "osint/dns_resolve" in names

    def test_get_module_whois(self):
        """get_module('osint/whois_lookup') returns a WhoisLookup instance."""
        pm = PluginManager()
        pm.load_plugins()
        mod = pm.get_module("osint/whois_lookup")
        assert mod is not None
        assert isinstance(mod, WhoisLookup)

    def test_get_module_dns(self):
        """get_module('osint/dns_resolve') returns a DnsResolve instance."""
        pm = PluginManager()
        pm.load_plugins()
        mod = pm.get_module("osint/dns_resolve")
        assert mod is not None
        assert isinstance(mod, DnsResolve)

    def test_get_module_unknown_returns_none(self):
        """get_module() for unknown path returns None."""
        pm = PluginManager()
        pm.load_plugins()
        assert pm.get_module("osint/nonexistent") is None

    def test_search_whois(self):
        """search('whois') finds the whois module."""
        pm = PluginManager()
        pm.load_plugins()
        results = pm.search("whois")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "osint/whois_lookup" in names

    def test_search_dns(self):
        """search('dns') finds the dns module."""
        pm = PluginManager()
        pm.load_plugins()
        results = pm.search("dns")
        assert len(results) >= 1
        names = [r["name"] for r in results]
        assert "osint/dns_resolve" in names

    def test_search_no_match_returns_empty(self):
        """search with no match returns empty list."""
        pm = PluginManager()
        pm.load_plugins()
        results = pm.search("xxxxxxnonexistentxxxxxx")
        assert results == []

    def test_list_modules_returns_both_builtins(self):
        """list_modules() returns at least the two built-in modules."""
        pm = PluginManager()
        pm.load_plugins()
        modules = pm.list_modules()
        assert len(modules) >= 2
        # Each entry should have name, description, type
        for m in modules:
            assert "name" in m
            assert "description" in m
            assert "type" in m

    def test_register_module_manual(self):
        """register_module() allows manual registration and retrieval."""
        pm = PluginManager()

        class TestModule(BaseModule):
            name = "test/custom"
            description = "Custom test module"
            author = "tester"
            module_type = "osint"

            async def hunt(self, target, options):
                return []

        pm.register_module("test/custom", TestModule)
        mod = pm.get_module("test/custom")
        assert mod is not None
        assert isinstance(mod, TestModule)

    def test_module_satisfies_protocol_after_load(self):
        """Modules retrieved via get_module() satisfy PursuitModule Protocol."""
        pm = PluginManager()
        pm.load_plugins()
        mod = pm.get_module("osint/whois_lookup")
        assert isinstance(mod, PursuitModule)

    def test_failed_module_load_does_not_crash(self):
        """A bad module class registered does not crash get_module().

        Simulates a module that raises on instantiation. The PluginManager
        should log the error and return None gracefully.
        """
        pm = PluginManager()
        pm.load_plugins()

        class BrokenModule(BaseModule):
            name = "broken/module"

            def __init__(self):
                raise RuntimeError("Broken on init")

        # Register the broken class — it won't fail at registration time
        pm.register_module("broken/module", BrokenModule)
        # Getting it should fail gracefully, returning None
        mod = pm.get_module("broken/module")
        assert mod is None

    def test_production_sequence_load_then_search_then_get(self):
        """Exercise the production sequence: load -> search -> get -> initialize -> hunt stub."""
        pm = PluginManager()
        pm.load_plugins()

        results = pm.search("dns")
        assert len(results) >= 1

        mod = pm.get_module(results[0]["name"])
        assert mod is not None
        mod.initialize({})
        assert mod._config == {}


# ---------------------------------------------------------------------------
# Built-in module hunt() integration tests (real network)
# ---------------------------------------------------------------------------

class TestWhoisLookupHunt:
    """WhoisLookup.hunt() against real example.com (uses system whois or socket)."""

    async def test_hunt_returns_list(self):
        """hunt() returns a non-empty list for example.com."""
        module = WhoisLookup()
        module.initialize({})
        results = await module.hunt("example.com", {})
        assert isinstance(results, list)
        assert len(results) >= 1

    async def test_hunt_result_has_stix_type(self):
        """Each result dict must have a 'type' key (STIX SCO pattern)."""
        module = WhoisLookup()
        module.initialize({})
        results = await module.hunt("example.com", {})
        for r in results:
            assert "type" in r

    async def test_hunt_result_has_value(self):
        """Each result dict must have a 'value' key with the target."""
        module = WhoisLookup()
        module.initialize({})
        results = await module.hunt("example.com", {})
        # At least one result should contain the domain name
        values = [r.get("value", "") for r in results]
        assert any("example" in str(v) for v in values)

    async def test_hunt_with_ip_target(self):
        """hunt() can accept an IP address as target."""
        module = WhoisLookup()
        module.initialize({})
        results = await module.hunt("8.8.8.8", {})
        assert isinstance(results, list)
        assert len(results) >= 1


class TestDnsResolveHunt:
    """DnsResolve.hunt() against real example.com using socket.getaddrinfo."""

    async def test_hunt_returns_list(self):
        """hunt() returns a non-empty list for example.com."""
        module = DnsResolve()
        module.initialize({})
        results = await module.hunt("example.com", {})
        assert isinstance(results, list)
        assert len(results) >= 1

    async def test_hunt_result_has_stix_type(self):
        """Each result dict must have a 'type' key."""
        module = DnsResolve()
        module.initialize({})
        results = await module.hunt("example.com", {})
        for r in results:
            assert "type" in r

    async def test_hunt_returns_ipv4_addr(self):
        """At least one result should be an ipv4-addr SCO."""
        module = DnsResolve()
        module.initialize({})
        results = await module.hunt("example.com", {})
        types = [r.get("type") for r in results]
        assert "ipv4-addr" in types

    async def test_hunt_returns_domain_name(self):
        """At least one result should be a domain-name SCO."""
        module = DnsResolve()
        module.initialize({})
        results = await module.hunt("example.com", {})
        types = [r.get("type") for r in results]
        assert "domain-name" in types

    async def test_hunt_domain_name_has_value(self):
        """domain-name result must have value matching target."""
        module = DnsResolve()
        module.initialize({})
        results = await module.hunt("example.com", {})
        domain_results = [r for r in results if r.get("type") == "domain-name"]
        assert len(domain_results) >= 1
        assert domain_results[0]["value"] == "example.com"

    async def test_hunt_with_options_record_type(self):
        """hunt() accepts RECORD_TYPE option."""
        module = DnsResolve()
        module.initialize({})
        results = await module.hunt("example.com", {"RECORD_TYPE": "A"})
        assert isinstance(results, list)
        assert len(results) >= 1
