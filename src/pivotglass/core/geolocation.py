"""Local IP geolocation and ASN from DB-IP Lite databases.

@decision DEC-GEO-LOCAL-001
@title Every IP is geolocated locally; no case IP leaves the machine for location
@status accepted
@rationale Owner decision 2026-11-21 (docs/plans/V1.4.0_ENRICHMENT_STORY_PLAN.md).
           DB-IP Lite city and ASN databases (CC BY 4.0, keyless, monthly) are
           downloaded only when the analyst asks, stored under
           ~/.pivotglass/geo/, and read with maxminddb. Lookups are local and
           deterministic. The result is labelled with the database edition so
           it stays distinguishable from a source-reported location, and it
           describes infrastructure location, never actor origin. Attribution is
           required by the licence and is shown wherever the data appears.
"""

from __future__ import annotations

import gzip
import ipaddress
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import maxminddb

ATTRIBUTION = "IP geolocation by DB-IP (https://db-ip.com), CC BY 4.0"
DOWNLOAD_BASE = "https://download.db-ip.com/free"
DATABASES = {"city": "dbip-city-lite", "asn": "dbip-asn-lite"}
_META = "edition.json"


def default_geo_dir() -> Path:
    """``PIVOTGLASS_GEO_DIR`` when set (tests, shared installs), else ~/.pivotglass/geo."""
    override = os.environ.get("PIVOTGLASS_GEO_DIR")
    return Path(override) if override else Path.home() / ".pivotglass" / "geo"


@dataclass(frozen=True)
class GeoRecord:
    ip: str
    country_code: str
    country_name: str
    region: str
    city: str
    asn: int | None
    as_org: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _editions(now: datetime) -> list[str]:
    """This month's edition, then last month's (published on the 1st, sometimes late)."""
    previous = now.replace(day=1) - timedelta(days=1)
    return [now.strftime("%Y-%m"), previous.strftime("%Y-%m")]


class GeoDatabase:
    """Reader and updater for the local DB-IP Lite databases."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_geo_dir()

    def path(self, kind: str) -> Path:
        return self.directory / f"{DATABASES[kind]}.mmdb"

    def status(self) -> dict[str, Any]:
        meta_path = self.directory / _META
        meta = json.loads(meta_path.read_text()) if meta_path.is_file() else {}
        present = all(self.path(kind).is_file() for kind in DATABASES)
        return {
            "present": present,
            "edition": meta.get("edition") if present else None,
            "downloaded_at": meta.get("downloaded_at") if present else None,
            "directory": str(self.directory),
            "attribution": ATTRIBUTION,
        }

    def source_label(self) -> str:
        edition = self.status().get("edition") or "unknown edition"
        return f"DB-IP Lite {edition} (local)"

    def update(self, *, now: datetime | None = None, client: httpx.Client | None = None) -> dict[str, Any]:
        """Download the newest available edition of both databases, atomically."""
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        owned = client is None
        http = client or httpx.Client(timeout=120.0, follow_redirects=True)
        try:
            last_error = ""
            for edition in _editions(now or datetime.now(UTC)):
                staged: dict[str, Path] = {}
                try:
                    for kind, stem in DATABASES.items():
                        staged[kind] = self._fetch(http, f"{DOWNLOAD_BASE}/{stem}-{edition}.mmdb.gz")
                except (httpx.HTTPError, OSError, maxminddb.InvalidDatabaseError, ValueError) as exc:
                    last_error = f"{edition}: {exc}"
                    for path in staged.values():
                        path.unlink(missing_ok=True)
                    continue
                for kind, path in staged.items():
                    os.replace(path, self.path(kind))
                (self.directory / _META).write_text(json.dumps({
                    "edition": edition,
                    "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "attribution": ATTRIBUTION,
                }))
                _reader.cache_clear()
                return self.status()
            raise RuntimeError(f"No DB-IP Lite edition could be downloaded ({last_error})")
        finally:
            if owned:
                http.close()

    def _fetch(self, http: httpx.Client, url: str) -> Path:
        handle, name = tempfile.mkstemp(dir=self.directory, suffix=".mmdb.part")
        os.close(handle)
        target = Path(name)
        try:
            with http.stream("GET", url) as response:
                response.raise_for_status()
                with tempfile.TemporaryFile() as compressed:
                    for chunk in response.iter_bytes():
                        compressed.write(chunk)
                    compressed.seek(0)
                    with gzip.GzipFile(fileobj=compressed) as source, target.open("wb") as sink:
                        shutil.copyfileobj(source, sink)
            maxminddb.open_database(str(target)).close()  # reject a truncated or wrong file
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target

    def lookup(self, ip: str) -> GeoRecord | None:
        """Return the local record for a public IP, or None (private, unknown, no data)."""
        try:
            address = ipaddress.ip_address(ip.strip())
        except ValueError:
            return None
        if not address.is_global:
            return None
        city_path, asn_path = self.path("city"), self.path("asn")
        if not (city_path.is_file() and asn_path.is_file()):
            return None
        city = _reader(str(city_path), city_path.stat().st_mtime).get(str(address)) or {}
        asn = _reader(str(asn_path), asn_path.stat().st_mtime).get(str(address)) or {}
        country = city.get("country") or {}
        code = str(country.get("iso_code") or "")
        if not code and not asn:
            return None
        subdivisions = city.get("subdivisions") or [{}]
        return GeoRecord(
            ip=str(address),
            country_code=code.upper(),
            country_name=str((country.get("names") or {}).get("en") or ""),
            region=str((subdivisions[0].get("names") or {}).get("en") or ""),
            city=str(((city.get("city") or {}).get("names") or {}).get("en") or ""),
            asn=asn.get("autonomous_system_number"),
            as_org=str(asn.get("autonomous_system_organization") or ""),
            source=self.source_label(),
        )


@lru_cache(maxsize=4)
def _reader(path: str, mtime: float) -> Any:
    """Memory-mapped reader, reopened when the file is replaced (mtime key)."""
    return maxminddb.open_database(path, maxminddb.MODE_MMAP)


def flag_emoji(country_code: str) -> str:
    """Regional-indicator flag for an ISO 3166-1 alpha-2 code ('' if not two letters)."""
    code = country_code.strip().upper()
    if len(code) != 2 or not code.isascii() or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in code)
