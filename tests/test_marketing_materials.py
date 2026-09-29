"""Publication constraints for the public, versioned marketing kit."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKETING = ROOT / "docs" / "marketing"


def test_mastodon_copy_fits_public_post_limit():
    content = (MARKETING / "MASTODON.md").read_text()
    match = re.search(r"<!-- post:start -->\n(.*?)\n<!-- post:end -->", content, re.DOTALL)
    assert match is not None, "The publication text must have an unambiguous extraction boundary."
    post = match.group(1)
    assert 0 < len(post) <= 500
    assert "https://github.com/jarocki/pivotglass" in post


def test_required_marketing_deliverables_are_not_ignored():
    names = {
        "README.md", "PRODUCT_ONE_PAGER.md", "ELEVATOR_PITCHES.md",
        "LINKEDIN.md", "MASTODON.md", "SIGNAL.md", "WEBSITE_COPY.md",
        "LAUNCH_CHECKLIST.md",
    }
    for name in names:
        path = MARKETING / name
        assert path.is_file(), f"Missing public material: {name}"
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", str(path.relative_to(ROOT))],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 1, f"Public material is ignored: {name}: {result.stdout}"
