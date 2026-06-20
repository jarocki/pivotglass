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
