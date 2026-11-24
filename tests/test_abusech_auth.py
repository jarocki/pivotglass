"""abuse.ch Auth-Key (#20, DEC-ABUSECH-AUTH-001): one key, three services, missing key is "not configured"."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from pivotglass.core.config import ConfigManager
from pivotglass.core.module_config import ServiceDisabledError, resolve_module_credentials
from pivotglass.modules.base import AuthenticationError
from pivotglass.modules.cti.malwarebazaar import MalwareBazaar
from pivotglass.modules.cti.threatfox import ThreatFox
from pivotglass.modules.cti.urlhaus import URLHaus

MODULES = {"cti/threatfox": ThreatFox, "cti/urlhaus": URLHaus, "cti/malwarebazaar": MalwareBazaar}


def _hunt(module, target, handler, monkeypatch):
    """Run hunt() with every AsyncClient routed through *handler* (real httpx request objects)."""
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler)))
    return asyncio.run(module.hunt(target, {}))


@pytest.mark.parametrize("cls", MODULES.values())
def test_missing_key_is_a_not_configured_error_naming_the_env_var(cls, monkeypatch):
    module = cls()
    module.initialize({})
    with pytest.raises(AuthenticationError, match="not configured.*PIVOTGLASS_ABUSECH_API_KEY"):
        _hunt(module, "d41d8cd98f00b204e9800998ecf8427e", lambda r: httpx.Response(200), monkeypatch)


@pytest.mark.parametrize(
    ("cls", "target", "host", "body_check"),
    [
        (ThreatFox, "evil.example", "threatfox-api.abuse.ch",
         lambda r: json.loads(r.content) == {"query": "search_ioc", "search_term": "evil.example"}),
        (URLHaus, "evil.example", "urlhaus-api.abuse.ch",
         lambda r: r.url.path == "/v1/host/" and parse_qs(r.content.decode()) == {"host": ["evil.example"]}),
        (MalwareBazaar, "d41d8cd98f00b204e9800998ecf8427e", "mb-api.abuse.ch",
         lambda r: parse_qs(r.content.decode())["query"] == ["get_info"]),
    ],
)
def test_key_travels_in_the_auth_key_header_to_the_service_host(cls, target, host, body_check, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"query_status": "no_results"})

    module = cls()
    module.initialize({"api_key": "k-123"})
    assert _hunt(module, target, handler, monkeypatch) == []
    request = seen[0]
    assert request.headers["Auth-Key"] == "k-123"
    assert request.url.host == host and request.url.scheme == "https"
    assert "k-123" not in str(request.url)
    assert body_check(request)


@pytest.mark.parametrize("status", [401, 403])
def test_rejected_key_is_an_authentication_fault(status, monkeypatch):
    module = ThreatFox()
    module.initialize({"api_key": "wrong"})
    with pytest.raises(AuthenticationError, match=f"rejected the abuse.ch API key \\(HTTP {status}\\)"):
        _hunt(module, "evil.example",
              lambda r: httpx.Response(status, json={"query_status": "unknown_auth_key"}), monkeypatch)


def test_base_url_override_reaches_the_request(monkeypatch):
    seen = []
    module = URLHaus()
    module.initialize({"api_key": "k", "base_url": "https://gw.example/urlhaus"})
    _hunt(module, "https://evil.example/x",
          lambda r: seen.append(r) or httpx.Response(200, json={"query_status": "no_results"}), monkeypatch)
    assert str(seen[0].url) == "https://gw.example/urlhaus/url/"


def test_one_stored_key_reaches_all_three_and_each_keeps_its_own_toggle(tmp_path: Path):
    config = ConfigManager(config_dir=tmp_path)
    config.set("api_keys.abusech", "shared-key")
    for path in MODULES:
        assert resolve_module_credentials(path, config) == {"api_key": "shared-key"}
    config.set_service_enabled("urlhaus", False)
    with pytest.raises(ServiceDisabledError):
        resolve_module_credentials("cti/urlhaus", config)
    assert resolve_module_credentials("cti/threatfox", config) == {"api_key": "shared-key"}


def test_env_var_supplies_the_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PIVOTGLASS_ABUSECH_API_KEY", "env-key")
    assert resolve_module_credentials("cti/malwarebazaar", ConfigManager(config_dir=tmp_path)) == {
        "api_key": "env-key"
    }


def test_web_hunt_records_a_missing_abusech_key_as_not_configured(tmp_path: Path, monkeypatch):
    from pivotglass.web.server import _unconfigured_service

    for name in ("PIVOTGLASS_ABUSECH_API_KEY", "ABUSECH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    config = ConfigManager(config_dir=tmp_path)
    failure = {"category": "API key", "next_action": "Set PIVOTGLASS_ABUSECH_API_KEY or run setup."}
    assert _unconfigured_service(failure, config, "ThreatFox") == "ThreatFox"
    config.set("api_keys.abusech", "present")
    assert _unconfigured_service(failure, config, "ThreatFox") is None  # a rejected key stays a fault


def test_credential_check_posts_where_the_api_requires_it(monkeypatch):
    from pivotglass.agent import provider_setup
    from pivotglass.agent.provider_setup import CTI_SERVICES, _validate_cti_key

    calls = []

    def fake_post(url, headers=None, json=None, data=None, timeout=None):
        calls.append(("POST", url, headers, json, data))
        return httpx.Response(403, text='{"query_status": "unknown_auth_key"}')

    def fake_get(url, headers=None, timeout=None, follow_redirects=None):
        calls.append(("GET", url, headers, None, None))
        return httpx.Response(200, json={"query_status": "ok"})

    monkeypatch.setattr(provider_setup.httpx, "post", fake_post)
    monkeypatch.setattr(provider_setup.httpx, "get", fake_get)
    specs = {spec.id: spec for spec in CTI_SERVICES}

    assert _validate_cti_key(specs["threatfox"], ["bogus"]) == (
        False, "Authentication failed (abuse.ch does not recognise this Auth-Key)")
    assert calls[-1][:2] == ("POST", "https://threatfox-api.abuse.ch/api/v1/")
    assert calls[-1][2]["Auth-Key"] == "bogus" and calls[-1][3] == {"query": "get_iocs", "days": 1}

    _validate_cti_key(specs["malwarebazaar"], ["bogus"])
    assert calls[-1][0] == "POST" and calls[-1][4] == {"query": "get_recent", "selector": "time"}

    assert _validate_cti_key(specs["urlhaus"], ["good"]) == (True, "Validated successfully")
    assert calls[-1][:2] == ("GET", "https://urlhaus-api.abuse.ch/v1/urls/recent/limit/1/")
