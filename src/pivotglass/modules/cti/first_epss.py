"""FIRST EPSS module: exploit-prediction score for a CVE (keyless).

API: GET {base}/data/v1/epss?cve=CVE-...  (base default https://api.first.org)
Docs: https://www.first.org/epss/api

@decision DEC-MODULE-FIRST-EPSS-001
@title EPSS is a probability estimate with its model date; no data is an empty result
@status accepted
@rationale The API answers ``{"status": "OK", "total": N, "data": [{"cve", "epss",
           "percentile", "date"}]}`` with ``epss`` and ``percentile`` as decimal
           strings between 0 and 1 (verified 2026-11-27: CVE-2021-44228 returned
           epss "0.999990000", percentile "1.000000000", date "2026-11-26"). A CVE
           with no score returns HTTP 200 with ``data: []`` and yields ``[]``: absence
           of a score is not a score of zero. The result is one ``vulnerability`` dict
           with ``x_epss_score`` and ``x_epss_percentile`` as floats and
           ``x_epss_date`` (the model date the API returned, YYYY-MM-DD). EPSS
           estimates the probability of exploitation activity in the next 30 days
           from public signals; it is a prediction, not an observation, and is
           recorded as such under its own prefix (DEC-MODULE-VULNERABILITY-001).
"""

from __future__ import annotations

from typing import Any

import httpx

from pivotglass.modules.base import BaseModule, ModuleError
from pivotglass.modules.keyless_http import json_body, keyless_get, unexpected_status
from pivotglass.modules.vulnerability import cve_target, vulnerability_object

SOURCE = "FIRST EPSS"


def _unit_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ModuleError(f"{SOURCE} returned a non-numeric {field}; no result recorded.") from exc
    if not 0.0 <= number <= 1.0:
        raise ModuleError(f"{SOURCE} returned {field} outside 0-1; no result recorded.")
    return number


class FirstEpss(BaseModule):
    """EPSS exploit-prediction score and percentile for a CVE (no key)."""

    name = "cti/first_epss"
    description = "Exploit Prediction Scoring System score and percentile via FIRST (no key)"
    author = "Pivotglass"
    module_type = "cti"
    service_id = "first_epss"
    accepts = ("cve",)
    requires_api_key = False
    transport: httpx.AsyncBaseTransport | None = None

    def __init__(self) -> None:
        super().__init__()
        self.options: dict[str, Any] = {
            "TARGET": {"required": True, "description": "CVE identifier (CVE-YYYY-NNNN)", "default": ""},
        }

    async def hunt(self, target: str, options: dict[str, Any]) -> list[dict]:
        cve = cve_target(SOURCE, target)
        response = await keyless_get(
            SOURCE, f"{self.base_url}/data/v1/epss", params={"cve": cve}, transport=self.transport
        )
        if response.status_code != 200:
            raise unexpected_status(SOURCE, response)
        body = json_body(SOURCE, response)
        rows = body.get("data") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise ModuleError(f"{SOURCE} returned an unexpected response shape; no result recorded.")
        row = next((r for r in rows if isinstance(r, dict) and str(r.get("cve", "")).upper() == cve), None)
        if row is None:
            return []
        return [
            vulnerability_object(
                cve,
                x_epss_score=_unit_float(row.get("epss"), "epss"),
                x_epss_percentile=_unit_float(row.get("percentile"), "percentile"),
                x_epss_date=str(row.get("date") or ""),
            )
        ]
