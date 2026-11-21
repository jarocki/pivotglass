"""Suite-wide isolation from the developer's machine."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_local_geolocation(tmp_path_factory, monkeypatch):
    # Local DB-IP data under ~/.pivotglass/geo would make visualization results
    # depend on the machine; tests see an empty geo directory unless they install one.
    monkeypatch.setenv("PIVOTGLASS_GEO_DIR", str(tmp_path_factory.mktemp("geo-empty")))
