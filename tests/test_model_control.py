"""Model/API control and asynchronous configuration-advisor contracts."""

from pathlib import Path

import pytest

from adversary_pursuit.agent.configuration_advisor import ConfigurationAdvisor
from adversary_pursuit.agent.model_control import (
    ModelControl,
    execute_configuration_command,
    execute_model_command,
)
from adversary_pursuit.core.config import ConfigManager


def _control(tmp_path: Path) -> ModelControl:
    return ModelControl(ConfigManager(config_dir=tmp_path))


def test_status_is_masked_and_reports_effective_selection(tmp_path, monkeypatch):
    monkeypatch.delenv("AP_MODEL", raising=False)
    control = _control(tmp_path)
    control.config_mgr.set_agent_selection("openai", "gpt-test")
    control.config_mgr.set_provider_api_key("openai", "super-secret-value")

    status = control.status()
    summary = control.configuration_summary()

    assert status["model"] == "gpt-test"
    assert status["credential_source"] == "config"
    assert "super-secret-value" not in repr(summary)
    assert "agent_openai" not in repr(summary)


def test_model_show_enable_disable_and_advisor_commands_are_local(tmp_path):
    control = _control(tmp_path)

    shown = execute_model_command(("show",), control)
    disabled = execute_model_command(("disable",), control)
    advisor = execute_model_command(("advisor", "off"), control)

    assert "MODEL CONFIGURATION" in shown
    assert "disabled" in disabled.lower()
    assert control.config_mgr.is_agent_enabled() is False
    assert "disabled" in advisor.lower()
    assert control.config_mgr.is_configuration_advisor_enabled() is False


def test_model_catalog_and_selection_use_provider_visible_models(
    tmp_path, monkeypatch
):
    control = _control(tmp_path)
    control.config_mgr.set_agent_selection("ollama", "ollama/old")
    monkeypatch.setattr(
        "adversary_pursuit.agent.model_control.list_models",
        lambda provider, key: ["qwen-test:8b", "reasoner-test:14b"],
    )
    monkeypatch.setattr(
        "adversary_pursuit.agent.model_control._capability_info",
        lambda model: {
            "supports_function_calling": True,
            "supports_reasoning": "reasoner" in model,
            "max_input_tokens": 128_000,
        },
    )

    listing = execute_model_command(("list",), control)
    selected = execute_model_command(("select", "qwen-test:8b"), control)

    assert "2 visible" in listing
    assert "Structured tool calling" in listing
    assert "ollama/qwen-test:8b" in selected
    assert control.config_mgr.get_agent_model() == "ollama/qwen-test:8b"


def test_model_selection_rejects_unlisted_model(tmp_path, monkeypatch):
    control = _control(tmp_path)
    control.config_mgr.set_agent_selection("ollama", "ollama/old")
    monkeypatch.setattr(
        "adversary_pursuit.agent.model_control.list_models",
        lambda provider, key: ["approved:latest"],
    )

    with pytest.raises(ValueError, match="was not returned"):
        control.select_model("invented:latest")


def test_api_enable_disable_and_repair_are_persistent(tmp_path):
    control = _control(tmp_path)

    assert "disabled" in execute_configuration_command(
        ("disable", "virustotal"), control
    )
    assert control.config_mgr.is_service_enabled("virustotal") is False
    assert "VirusTotal is disabled" in execute_configuration_command(
        ("repair",), control
    )
    execute_configuration_command(("enable", "virustotal"), control)
    assert ConfigManager(config_dir=tmp_path).is_service_enabled("virustotal") is True


def test_advisor_is_throttled_character_narration_and_spends_no_tokens(tmp_path):
    control = _control(tmp_path)
    now = [100.0]
    advisor = ConfigurationAdvisor(
        control,
        interval_seconds=300,
        clock=lambda: now[0],
    )

    first = advisor.poll("the_computer")
    second = advisor.poll("the_computer")
    now[0] += 301
    third = advisor.poll("full_troll")

    assert first is not None
    assert first.content_class == "narration"
    assert first.evidence is False
    assert "Dave" in first.message or "operational" in first.message
    assert second is None
    assert third is not None
    assert "🙄" in third.message or "documentation" in third.message


def test_advisor_can_be_disabled_without_deleting_configuration(tmp_path):
    control = _control(tmp_path)
    control.config_mgr.set_configuration_advisor_enabled(False)

    assert ConfigurationAdvisor(control).poll("default") is None
