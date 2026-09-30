"""Model/API control and asynchronous configuration-advisor contracts."""

from pathlib import Path

import pytest

from pivotglass.agent.configuration_advisor import ConfigurationAdvisor
from pivotglass.agent.model_control import (
    ModelControl,
    execute_configuration_command,
    execute_model_command,
)
from pivotglass.core.config import ConfigManager
from pivotglass.core.module_credentials import resolve_module_credentials


def _control(tmp_path: Path) -> ModelControl:
    return ModelControl(ConfigManager(config_dir=tmp_path))


def test_service_credential_is_saved_when_validation_is_unreachable(tmp_path, monkeypatch):
    control = _control(tmp_path)
    monkeypatch.setattr(
        "pivotglass.agent.model_control._validate_cti_key",
        lambda spec, values: (False, "Network unreachable; access is unverified"),
    )

    result = control.set_service_credentials("virustotal", ["example-secret"])

    assert result.state == "unreachable"
    assert control.config_mgr.get_api_key("virustotal") == "example-secret"
    assert "example-secret" not in repr(result)


def test_service_credential_can_be_saved_without_a_live_test(tmp_path, monkeypatch):
    control = _control(tmp_path)
    monkeypatch.setattr(
        "pivotglass.agent.model_control._validate_cti_key",
        lambda spec, values: pytest.fail("Live test should not run"),
    )

    result = control.set_service_credentials("virustotal", ["example-secret"], verify=False)

    assert result.state == "unknown"
    assert control.config_mgr.get_api_key("virustotal") == "example-secret"


def test_service_check_uses_stored_fields_when_inputs_are_blank(tmp_path, monkeypatch):
    control = _control(tmp_path)
    control.config_mgr.set("api_keys.passivetotal_user", "analyst@example.test")
    control.config_mgr.set("api_keys.passivetotal_key", "stored-secret")
    seen = []
    monkeypatch.setattr(
        "pivotglass.agent.model_control._validate_cti_key",
        lambda spec, values: (seen.append(values) or True, "Validated successfully"),
    )

    assert control.check_service("passivetotal", ["", ""]).state == "ready"
    assert seen == [["analyst@example.test", "stored-secret"]]


def test_service_configuration_reports_each_field_without_exposing_values(tmp_path):
    control = _control(tmp_path)
    control.config_mgr.set("api_keys.passivetotal_user", "analyst@example.test")

    service = next(item for item in control.configuration_summary()["services"] if item["id"] == "passivetotal")

    assert service["credential_source"] == "missing"
    assert [field["credential_source"] for field in service["credential_fields"]] == ["config", "missing"]
    assert "analyst@example.test" not in repr(service)


def test_censys_org_id_is_optional_and_can_be_added_to_stored_pat(tmp_path, monkeypatch):
    control = _control(tmp_path)
    seen = []
    monkeypatch.setattr(
        "pivotglass.agent.model_control._validate_cti_key",
        lambda spec, values: (seen.append(values) or True, "Validated successfully"),
    )

    first = control.set_service_credentials("censys_pat", ["pat-secret", ""])
    second = control.set_service_credentials("censys_pat", ["", "org-123"])

    assert first.state == second.state == "ready"
    assert seen == [["pat-secret", ""], ["pat-secret", "org-123"]]
    assert control.config_mgr.get_api_key("censys_pat") == "pat-secret"
    assert control.config_mgr.get_api_key("censys_org_id") == "org-123"


@pytest.mark.parametrize(
    ("service_id", "module_path", "fields"),
    [
        ("shodan", "osint/shodan_ip", ["shodan"]),
        ("virustotal", "cti/virustotal", ["virustotal"]),
        ("abuseipdb", "osint/abuseipdb", ["abuseipdb"]),
        ("hibp", "osint/hibp", ["hibp"]),
        ("otx", "cti/otx", ["otx"]),
        ("urlscan", "osint/urlscan", ["urlscan"]),
        ("censys_pat", "osint/censys_host", ["censys_pat", "censys_org_id"]),
        ("greynoise", "osint/greynoise", ["greynoise"]),
        ("passivetotal", "cti/passivetotal", ["passivetotal_user", "passivetotal_key"]),
    ],
)
def test_every_service_saved_credential_reaches_its_module(
    tmp_path, monkeypatch, service_id, module_path, fields
):
    control = _control(tmp_path)
    values = [f"example-{field}" for field in fields]
    monkeypatch.setattr(
        "pivotglass.agent.model_control._validate_cti_key",
        lambda spec, credentials: (True, "Validated successfully"),
    )
    control.config_mgr.set_service_enabled(service_id, True)

    assert control.set_service_credentials(service_id, values).state == "ready"
    module_config = resolve_module_credentials(module_path, control.config_mgr)

    if service_id == "censys_pat":
        assert module_config == dict(zip(fields, values))
    elif service_id == "passivetotal":
        assert module_config == dict(zip(fields, values))
    else:
        assert module_config == {"api_key": values[0]}


def test_status_is_masked_and_reports_effective_selection(tmp_path, monkeypatch):
    monkeypatch.delenv("PIVOTGLASS_MODEL", raising=False)
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
        "pivotglass.agent.model_control.list_models",
        lambda provider, key: ["qwen-test:8b", "reasoner-test:14b"],
    )
    monkeypatch.setattr(
        "pivotglass.agent.model_control._capability_info",
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
        "pivotglass.agent.model_control.list_models",
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
