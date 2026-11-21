"""Local geolocation (DEC-GEO-LOCAL-001): lookups never leave the machine."""

from __future__ import annotations

import gzip
from datetime import UTC, datetime

import httpx
import pytest

from pivotglass.core import geolocation
from pivotglass.core.geolocation import GeoDatabase, flag_emoji


class _FakeReader:
    def __init__(self, records):
        self.records = records

    def get(self, ip):
        return self.records.get(ip)


def _install(tmp_path, monkeypatch, city, asn, edition="2026-11"):
    db = GeoDatabase(tmp_path)
    tmp_path.mkdir(exist_ok=True)
    db.path("city").write_bytes(b"city")
    db.path("asn").write_bytes(b"asn")
    (tmp_path / "edition.json").write_text(f'{{"edition": "{edition}"}}')
    readers = {str(db.path("city")): _FakeReader(city), str(db.path("asn")): _FakeReader(asn)}
    monkeypatch.setattr(geolocation, "_reader", lambda path, mtime: readers[path])
    return db


def test_lookup_maps_city_and_asn_records_and_labels_the_edition(tmp_path, monkeypatch):
    db = _install(
        tmp_path / "geo",
        monkeypatch,
        city={"154.86.17.52": {
            "country": {"iso_code": "hk", "names": {"en": "Hong Kong"}},
            "subdivisions": [{"names": {"en": "Central and Western"}}],
            "city": {"names": {"en": "Hong Kong"}},
        }},
        asn={"154.86.17.52": {"autonomous_system_number": 140227,
                              "autonomous_system_organization": "HKCIC"}},
    )

    record = db.lookup(" 154.86.17.52 ")

    assert record is not None
    assert (record.country_code, record.city, record.asn, record.as_org) == ("HK", "Hong Kong", 140227, "HKCIC")
    assert record.source == "DB-IP Lite 2026-11 (local)"


@pytest.mark.parametrize("value", ["10.0.0.1", "127.0.0.1", "192.168.1.9", "not-an-ip", "fe80::1"])
def test_private_and_invalid_addresses_are_not_looked_up(tmp_path, monkeypatch, value):
    db = _install(tmp_path / "geo", monkeypatch, city={}, asn={})
    assert db.lookup(value) is None


def test_lookup_without_downloaded_data_returns_none(tmp_path):
    assert GeoDatabase(tmp_path / "missing").lookup("8.8.8.8") is None
    assert GeoDatabase(tmp_path / "missing").status()["present"] is False


def test_flag_emoji():
    assert flag_emoji("us") == "\U0001F1FA\U0001F1F8"
    assert flag_emoji("") == "" and flag_emoji("USA") == "" and flag_emoji("1A") == ""


def test_update_falls_back_to_last_month_and_replaces_atomically(tmp_path, monkeypatch):
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if "2026-12" in request.url.path:
            return httpx.Response(404)
        return httpx.Response(200, content=gzip.compress(b"fake-mmdb"))

    class _Opened:
        def close(self):
            pass

    monkeypatch.setattr(geolocation.maxminddb, "open_database", lambda path, *a: _Opened())
    db = GeoDatabase(tmp_path / "geo")
    status = db.update(now=datetime(2026, 12, 1, tzinfo=UTC), client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert status["present"] is True and status["edition"] == "2026-11"
    assert db.path("city").read_bytes() == b"fake-mmdb"
    assert requested[0].endswith("dbip-city-lite-2026-12.mmdb.gz")
    assert not list((tmp_path / "geo").glob("*.part"))
