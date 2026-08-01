"""Regression coverage for serving the current Pivotglass web export."""

from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler
from unittest.mock import MagicMock, call, patch

import pytest

from adversary_pursuit.web import server as web_server


def test_editable_checkout_rejects_export_older_than_source(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    output_dir = tmp_path / "out"
    app_dir.mkdir()
    output_dir.mkdir()
    source = app_dir / "page.tsx"
    exported = output_dir / "index.html"
    source.write_text("current source")
    exported.write_text("old export")
    os.utime(exported, ns=(1_000_000, 1_000_000))
    os.utime(source, ns=(2_000_000, 2_000_000))
    monkeypatch.setattr(web_server, "_SOURCE_WEB_DIR", tmp_path)
    monkeypatch.setattr(web_server, "_SOURCE_WEB_ROOT", output_dir)

    assert web_server._source_web_build_is_stale(output_dir) is True

    os.utime(exported, ns=(3_000_000, 3_000_000))
    assert web_server._source_web_build_is_stale(output_dir) is False


def test_local_static_responses_disable_browser_cache(tmp_path):
    service = web_server.WebCockpitService.__new__(web_server.WebCockpitService)
    handler_type = web_server._handler(service, tmp_path)
    handler = handler_type.__new__(handler_type)
    handler.path = "/"
    handler.send_header = MagicMock()

    with patch.object(SimpleHTTPRequestHandler, "end_headers"):
        handler.end_headers()

    assert handler.send_header.call_args_list == [
        call("Cache-Control", "no-store, max-age=0"),
        call("Pragma", "no-cache"),
        call("Expires", "0"),
    ]


def test_handler_accepts_only_explicitly_configured_hosts(tmp_path):
    service = web_server.WebCockpitService.__new__(web_server.WebCockpitService)
    handler_type = web_server._handler(
        service,
        tmp_path,
        allowed_hosts=frozenset({"127.0.0.1", "localhost", "192.168.4.58"}),
    )
    handler = handler_type.__new__(handler_type)

    handler.headers = {"Host": "192.168.4.58:8766"}
    assert handler._host_allowed() is True

    handler.headers = {"Host": "192.168.4.59:8766"}
    assert handler._host_allowed() is False


def test_web_server_rejects_wildcard_interface_binding():
    with pytest.raises(ValueError, match="wildcard interface binding"):
        web_server.run_web(host="0.0.0.0", open_browser=False)
