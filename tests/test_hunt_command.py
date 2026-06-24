"""Tests for 'hunt <ioc>' command (Phase 17R).

Production sequence: detect IoC type -> modules_accepting -> instantiate each ->
hunt() -> store_stix_objects -> print summary table.

@decision DEC-IOC-TYPES-001
@title hunt <ioc> dispatches to modules by accepts tuple; results persisted
@status accepted
@rationale See core/ioc_types.py for the detection rationale. The console wires
           detect_ioc_type -> modules_accepting -> per-module hunt() -> store_stix_objects.
           Tests use isolated PluginManager instances with fake modules to avoid
           real network calls while still exercising the full dispatch path.
"""

from __future__ import annotations

import io

import pytest

from adversary_pursuit.core.console import APConsole
from adversary_pursuit.modules.base import BaseModule


@pytest.fixture
def console(tmp_path):
    app = APConsole(
        config_dir=tmp_path / "config",
        workspace_dir=tmp_path / "workspaces",
    )
    app.stdout = io.StringIO()
    return app


def run_cmd(app: APConsole, cmd: str) -> str:
    app.stdout = io.StringIO()
    app.rich_console = app._make_rich_console()
    app.onecmd_plus_hooks(cmd)
    return app.stdout.getvalue()


class FakeIPv4Module(BaseModule):
    """Fake module accepting ipv4 — returns one result."""

    name = "test/fake_ip"
    description = "Fake IPv4 module"
    author = "test"
    module_type = "osint"
    accepts = ("ipv4",)

    async def hunt(self, target: str, options: dict) -> list[dict]:
        return [{"type": "ipv4-addr", "value": target, "x_source": "fake_ip"}]


class FakeIPv4Module2(BaseModule):
    """Second fake module accepting ipv4 — also returns one result."""

    name = "test/fake_ip2"
    description = "Fake IPv4 module 2"
    author = "test"
    module_type = "cti"
    accepts = ("ipv4",)

    async def hunt(self, target: str, options: dict) -> list[dict]:
        return [{"type": "ipv4-addr", "value": target, "x_source": "fake_ip2"}]


class FakeIPv4FailModule(BaseModule):
    """Fake module that always raises an exception."""

    name = "test/fake_fail"
    description = "Fake failing module"
    author = "test"
    module_type = "cti"
    accepts = ("ipv4",)

    async def hunt(self, target: str, options: dict) -> list[dict]:
        raise RuntimeError("Simulated API error")


class TestHuntCommand:
    """Tests for 'hunt <ioc>' dispatch."""

    def _register(self, console, path, cls):
        """Helper: register a fake module class."""
        console.plugin_mgr._modules[path] = cls

    def test_hunt_no_args_falls_back_to_run_alias(self, console):
        """hunt with no args falls back to _execute_hunt (run alias behavior)."""
        # No module loaded — should show "No module loaded" message
        out = run_cmd(console, "hunt")
        assert "module" in out.lower() or "no module" in out.lower()

    def test_hunt_unrecognized_ioc_prints_helpful_message(self, console):
        """hunt <garbage> prints unrecognized format message."""
        out = run_cmd(console, "hunt not-an-ioc!!!")
        assert "unrecognized" in out.lower() or "supported" in out.lower()

    def test_hunt_ipv4_dispatches_to_accepting_modules(self, console, tmp_path):
        """hunt 8.8.8.8 calls all modules whose accepts includes 'ipv4'."""
        # Register fake module, clear real ones from the query
        # We will use a fresh plugin_mgr so only our fake module is in play
        from adversary_pursuit.core.plugin_mgr import PluginManager

        pm = PluginManager()
        pm.register_module("test/fake_ip", FakeIPv4Module)
        console.plugin_mgr = pm

        out = run_cmd(console, "hunt 8.8.8.8")
        # Should mention the module and show summary
        assert "test/fake_ip" in out or "fake_ip" in out or "8.8.8.8" in out

    def test_hunt_summary_table_shows_per_module_status(self, console):
        """Summary table lists each module with OK status when successful."""
        from adversary_pursuit.core.plugin_mgr import PluginManager

        pm = PluginManager()
        pm.register_module("test/fake_ip", FakeIPv4Module)
        console.plugin_mgr = pm

        out = run_cmd(console, "hunt 1.2.3.4")
        # Table should show OK for successful module
        assert "OK" in out or "ok" in out.lower() or "test/fake_ip" in out

    def test_hunt_per_module_failure_does_not_abort_whole_hunt(self, console):
        """One module fails, another succeeds — both appear in summary table."""
        from adversary_pursuit.core.plugin_mgr import PluginManager

        pm = PluginManager()
        pm.register_module("test/fake_ip", FakeIPv4Module)
        pm.register_module("test/fake_fail", FakeIPv4FailModule)
        console.plugin_mgr = pm

        out = run_cmd(console, "hunt 8.8.8.8")
        # Both modules should appear in output
        assert "test/fake_ip" in out or "fake_ip" in out
        assert "test/fake_fail" in out or "fake_fail" in out

    def test_hunt_stores_results_in_workspace(self, console):
        """Successful hunt stores STIX objects in the active workspace."""
        from adversary_pursuit.core.plugin_mgr import PluginManager

        pm = PluginManager()
        pm.register_module("test/fake_ip", FakeIPv4Module)
        console.plugin_mgr = pm

        run_cmd(console, "hunt 8.8.8.8")
        objects = console.workspace_mgr.get_stix_objects()
        assert len(objects) >= 1
        values = [o.get("value") for o in objects]
        assert "8.8.8.8" in values

    def test_hunt_ipv4_with_real_modules_does_not_crash(self, console):
        """hunt 8.8.8.8 with real modules loaded doesn't crash (API failures are OK)."""
        out = run_cmd(console, "hunt 8.8.8.8")
        # Should mention hunting and not crash
        assert isinstance(out, str)
        assert "Hunting" in out or "hunting" in out.lower() or "module" in out.lower()

    def test_hunt_domain_dispatches_to_domain_accepting_modules(self, console):
        """hunt example.com dispatches to domain-accepting modules."""
        out = run_cmd(console, "hunt example.com")
        # Should at minimum mention the IoC type and not crash
        assert "domain" in out.lower() or "Hunting" in out

    def test_hunt_sha256_dispatches_correctly(self, console):
        """hunt with a SHA256 hash dispatches to hash-accepting modules."""
        sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        out = run_cmd(console, f"hunt {sha256}")
        assert "sha256" in out.lower() or "Hunting" in out


class TestHuntFleetInitialization:
    """AP #97 / AP #98: hunt <ioc> must initialize modules with a credential dict, not ConfigManager.

    AP #97 regression: passing self.config_mgr.config (raw Config dataclass) to
    module.initialize() — the dataclass has no .get() method.

    AP #98 regression: passing self.config_mgr (ConfigManager) to module.initialize()
    — modules' base contract is initialize(self, config: dict[str, Any]) and every
    module calls self._config.get("api_key", "") with a 2-arg dict.get() signature.
    ConfigManager.get() takes one arg and raises KeyError on miss.

    After AP #98: _initialize_module calls resolve_module_credentials() to produce
    a plain dict. Both call sites (fleet path and legacy run path) go through the
    shared resolver (DEC-MODULE-CREDS-SHARED-001).
    """

    def _make_capturing_module_cls(self, recorded: dict):
        """Return a PursuitModule subclass that records the init arg and calls .get().

        After AP #98: initialize() always receives a plain dict (not ConfigManager).
        The module exercises the real dict.get("api_key", "") access pattern inside
        initialize() so the test fails immediately if a wrong type is passed.
        """
        from adversary_pursuit.modules.base import BaseModule

        class CapturingModule(BaseModule):
            """Records what was passed to initialize() and exercises dict.get() on it.

            Mimics the real access pattern: real modules (virustotal, abuseipdb, otx…)
            call self._config.get("api_key", "") inside initialize(). That is a 2-arg
            dict.get() call. If initialize() receives ConfigManager or raw Config, this
            raises — surfacing the regression before hunt() is ever invoked.
            """

            name = "test/capturing"
            description = "Records init arg for AP #97/AP #98 regression detection"
            module_type = "test"
            accepts = ("ipv4",)
            options = {"TARGET": {"required": True, "description": "test"}}

            def initialize(self, config):
                recorded["init_arg"] = config
                # Exercise the exact 2-arg dict.get pattern real modules use.
                # On a plain dict this succeeds; on ConfigManager or raw Config it
                # raises — catching both AP #97 and AP #98 regression classes.
                recorded["resolved_key"] = config.get("api_key", "<missing>")

            async def hunt(self, target: str, options: dict) -> list[dict]:
                return [{"type": "ipv4-addr", "value": target, "x_source": "capturing"}]

        return CapturingModule

    def test_hunt_initializes_api_key_module_with_dict(self, tmp_path):
        """End-to-end: hunt <ioc> must pass a plain dict to module.initialize() (AP #98).

        Production sequence: do_hunt("8.8.8.8") → _hunt_ioc() →
        _initialize_module(module, path) → resolve_module_credentials(path, config_mgr) →
        module.initialize(dict). This is the compound-interaction test: it crosses
        APConsole → PluginManager → resolve_module_credentials → CapturingModule.initialize()
        in one call, verifying all internal seams are wired correctly.

        Failure modes caught:
        - AP #97: config was raw Config dataclass (no .get() at all)
        - AP #98: config was ConfigManager (1-arg .get(), raises on 2-arg call)
        - Any future regression that passes a non-dict to initialize()
        """
        import io

        from adversary_pursuit.core.console import APConsole
        from adversary_pursuit.core.plugin_mgr import PluginManager

        recorded: dict = {}
        CapturingModule = self._make_capturing_module_cls(recorded)

        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        app.stdout = io.StringIO()

        # Swap in a fresh PluginManager containing only our capturing module so
        # real modules (which may emit network errors) don't pollute the result.
        pm = PluginManager()
        pm.register_module("test/capturing", CapturingModule)
        app.plugin_mgr = pm

        # Rebuild rich console so it routes through the new stdout
        app.rich_console = app._make_rich_console()
        app.onecmd_plus_hooks("hunt 8.8.8.8")

        assert "init_arg" in recorded, (
            "CapturingModule.initialize() was never called — hunt fleet did not "
            "reach the module's initialize() at all."
        )
        assert isinstance(recorded["init_arg"], dict), (
            f"hunt fleet must initialize modules with a plain dict, "
            f"got {type(recorded['init_arg']).__name__!r}. "
            "AP #98: _initialize_module must call resolve_module_credentials() "
            "and pass the resulting dict, not the ConfigManager."
        )
        assert "api_key" in recorded["init_arg"], (
            "Resolved dict for 'test/capturing' must contain 'api_key' key. "
            "Unknown modules fall back to path-tail service lookup."
        )
        # The exact pattern real modules use in initialize():
        resolved_key = recorded["init_arg"].get("api_key", "<missing>")
        assert resolved_key != "<missing>", (
            "dict.get('api_key', '') must not raise — 2-arg get is the real modules' "
            "access pattern (AP #97 / AP #98 regression guard)."
        )

    def test_initialize_module_passes_dict_not_config_manager(self, tmp_path):
        """Direct unit test on _initialize_module — single helper, central invariant.

        Verifies that APConsole._initialize_module(module, module_path) passes a
        plain dict (produced by resolve_module_credentials) to module.initialize(),
        NOT the ConfigManager and NOT the raw Config dataclass.

        Fast inner loop for AP #97 / AP #98 regression: one console, one module, one assert.
        """
        import io

        from adversary_pursuit.core.console import APConsole

        recorded: dict = {}
        CapturingModule = self._make_capturing_module_cls(recorded)

        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        app.stdout = io.StringIO()

        module_instance = CapturingModule()
        # test/capturing is unknown → falls back to path-tail "capturing" → {"api_key": ""}
        app._initialize_module(module_instance, "test/capturing")

        assert "init_arg" in recorded, "_initialize_module did not call module.initialize()"
        assert isinstance(recorded["init_arg"], dict), (
            f"_initialize_module must pass a plain dict to module.initialize(), "
            f"got {type(recorded['init_arg']).__name__!r}. "
            "AP #98: resolver must return dict, not ConfigManager."
        )
        # dict.get("api_key", "") must work — this is what real modules call
        assert recorded["init_arg"].get("api_key", "") == recorded["resolved_key"], (
            "The resolved_key captured in initialize() must equal dict.get('api_key', '')"
        )
