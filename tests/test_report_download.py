"""Report export metadata stays attached to the generated case snapshot."""
from pivotglass import __version__
from pivotglass.agent.tools import ToolContext
from pivotglass.web.server import WebCockpitService


def test_report_result_carries_original_workspace_and_version_without_collecting(tmp_path):
    service = WebCockpitService(ToolContext(config_dir=tmp_path / "config", workspace_dir=tmp_path / "cases"))
    manager = service.ctx.workspace_mgr
    manager.create("report-case")
    manager.switch("report-case")
    manager.store_stix_objects([{"type": "domain-name", "value": "source.example"}], module_name="test/offline", target="source.example")
    observations = manager.get_observations()
    runs = manager.get_module_runs()
    result = service.execute_command("report")
    manager.switch("default")
    assert result["workspace"] == "report-case"
    assert result["version"] == __version__
    assert result["printable"] is True
    assert "source.example" in result["text"]
    manager.switch("report-case")
    assert manager.get_observations() == observations
    assert manager.get_module_runs() == runs
    assert service._runner is None
