"""Operational authority and degraded-state registry contracts."""

from adversary_pursuit.core.operational_status import build_authority_registry


def _configuration():
    return {
        "model": {
            "enabled": True,
            "credential_configured": False,
            "provider": "openai",
            "model": "openai/example",
            "credential_source": "missing",
        },
        "services": [
            {
                "id": "virustotal",
                "display_name": "VirusTotal",
                "enabled": True,
                "credential_source": "config",
                "credential_fields": [{"key": "virustotal", "label": "API key"}],
            },
            {
                "id": "shodan",
                "display_name": "Shodan",
                "enabled": True,
                "credential_source": "missing",
                "credential_fields": [{"key": "shodan", "label": "API key"}],
            },
            {
                "id": "crtsh",
                "display_name": "crt.sh",
                "enabled": False,
                "credential_source": "missing",
                "credential_fields": [],
            },
        ],
    }


def test_registry_distinguishes_ready_missing_disabled_and_degraded():
    registry = build_authority_registry(
        _configuration(),
        ["virustotal_lookup", "shodan_lookup", "crtsh_lookup"],
        [
            {
                "event_class": "source_fault",
                "tool": "virustotal_lookup",
            }
        ],
    )
    by_id = {row["id"]: row for row in registry["authorities"]}

    assert registry["state"] == "degraded"
    assert by_id["workspace"]["state"] == "ready"
    assert by_id["virustotal"]["state"] == "degraded"
    assert by_id["shodan"]["state"] == "missing_configuration"
    assert by_id["crtsh"]["state"] == "disabled"
    assert by_id["model_synthesis"]["state"] == "missing_configuration"
    assert all(row["background_network"] is False for row in registry["authorities"])
    assert "does not substitute model-generated telemetry" in registry["offline_behavior"]


def test_keyless_adapter_is_ready_without_credential():
    configuration = _configuration()
    service = configuration["services"][2]
    service["enabled"] = True
    registry = build_authority_registry(
        configuration,
        ["virustotal_lookup", "shodan_lookup", "crtsh_lookup"],
        [],
    )
    crtsh = next(row for row in registry["authorities"] if row["id"] == "crtsh")
    assert crtsh["state"] == "ready"
