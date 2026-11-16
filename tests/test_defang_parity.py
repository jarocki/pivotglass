"""The web client's defangValue mirrors defang_indicator_value; both read these cases."""

import json
from pathlib import Path

import pytest

from pivotglass.core.document_entity_extraction import defang_indicator_value

CASES = json.loads((Path(__file__).parent / "fixtures" / "defang_cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["value"][:24] for case in CASES])
def test_server_defang_matches_shared_cases(case):
    assert defang_indicator_value(case["value"], case["type"]) == case["expected"]
