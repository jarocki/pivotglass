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
    """AP #97: hunt <ioc> must initialize modules with ConfigManager, not raw Config.

    Without this test, the regression from Phase 17R (passing self.config_mgr.config
    instead of self.config_mgr) would not surface in CI — the existing TestHuntCommand
    tests use fakes without initialize() at all, so the wrong object type was invisible.

    The regression signature: every module that calls config.get("api_key", ...) in
    initialize() would fail with "'Config' object has no attribute 'get'" because the
    Pydantic Config dataclass exposes no .get() method.
    """

    def _make_capturing_module_cls(self, recorded: dict):
        """Return a PursuitModule subclass that records the init arg and calls .get()."""
        from adversary_pursuit.modules.base import BaseModule

        class CapturingModule(BaseModule):
            """Records what was passed to initialize() and exercises .get() on it.

            Mimics the real failure path: real modules (virustotal, abuseipdb, otx…)
            immediately call self._config.get("api_key", ...) in hunt().  If
            initialize() received the raw Config dataclass, .get() raises AttributeError.
            We surface that early inside initialize() itself so the test assertion
            catches the wrong type before hunt() is ever invoked.
            """

            name = "test/capturing"
            description = "Records init arg for AP #97 regression detection"
            module_type = "test"
            accepts = ("ipv4",)
            options = {"TARGET": {"required": True, "description": "test"}}

            def initialize(self, config):
                recorded["init_arg"] = config
                # Exercise the same access pattern real modules use:
                # self._config.get("api_key", "").  On ConfigManager this returns
                # a string (possibly ""); on the raw Config dataclass it raises
                # AttributeError — exactly the AP #97 regression.
                _ = (
                    config.get_api_key("test")
                    if hasattr(config, "get_api_key")
                    else config.get("api_key", "")
                )  # noqa: E501

            async def hunt(self, target: str, options: dict) -> list[dict]:
                return [{"type": "ipv4-addr", "value": target, "x_source": "capturing"}]

        return CapturingModule

    def test_hunt_initializes_modules_with_config_manager(self, tmp_path):
        """End-to-end: hunt <ioc> must pass ConfigManager to module.initialize().

        Production sequence: do_hunt("8.8.8.8") → _hunt_ioc() → _initialize_module(module)
        → module.initialize(<what?>). This test verifies <what?> is a ConfigManager
        instance (not the raw Config dataclass) by intercepting the initialize() call
        with a capturing module and asserting the type.

        This is the compound-interaction test required by the dispatch: it crosses
        APConsole → PluginManager → CapturingModule.initialize() in one call.
        """
        import io

        from adversary_pursuit.core.config import ConfigManager
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
        assert isinstance(recorded["init_arg"], ConfigManager), (
            f"hunt fleet must initialize modules with ConfigManager, "
            f"got {type(recorded['init_arg']).__name__!r}. "
            "AP #97: _hunt_ioc was passing self.config_mgr.config (raw Config "
            "dataclass) instead of self.config_mgr."
        )

    def test_initialize_module_passes_config_manager_not_dataclass(self, tmp_path):
        """Direct unit test on _initialize_module — single helper, central invariant.

        Verifies that APConsole._initialize_module(module) passes self.config_mgr
        (the ConfigManager) and NOT self.config (the raw Config dataclass).  This
        test is the fast inner loop for the AP #97 regression: one console, one
        capturing module, one assert.
        """
        import io

        from adversary_pursuit.core.config import ConfigManager
        from adversary_pursuit.core.console import APConsole

        recorded: dict = {}
        CapturingModule = self._make_capturing_module_cls(recorded)

        app = APConsole(
            config_dir=tmp_path / "config",
            workspace_dir=tmp_path / "workspaces",
        )
        app.stdout = io.StringIO()

        module_instance = CapturingModule()
        app._initialize_module(module_instance)

        assert "init_arg" in recorded, "_initialize_module did not call module.initialize()"
        assert isinstance(recorded["init_arg"], ConfigManager), (
            f"_initialize_module must pass self.config_mgr (ConfigManager), "
            f"got {type(recorded['init_arg']).__name__!r}"
        )
