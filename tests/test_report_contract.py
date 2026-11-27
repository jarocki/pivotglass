"""Report contract (#51): one vocabulary module, validated headers, honest defanging, reserved examples."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from pivotglass.core import analytic_ledger
from pivotglass.reports import contract as c

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def _header(**overrides):
    fields = dict(
        report_id="PG-TAA-2026-0001",
        type_id="threat-activity-alert",
        title="Threat Activity Alert",
        version=1,
        status=c.ReportStatus.DRAFT,
        issued_at=NOW,
        tlp=c.Tlp.AMBER,
        pap=c.Pap.AMBER,
        audience=("SOC analysts",),
        producer="Pivotglass",
        revision_history=(c.Revision(version=1, issued_at=NOW, status=c.ReportStatus.DRAFT, summary="First issue"),),
    )
    fields.update(overrides)
    return c.ReportHeader(**fields)


def test_estimative_scales_are_the_ledgers_own_not_copies():
    assert c.LikelihoodTerm is analytic_ledger.LikelihoodTerm
    assert c.ConfidenceLevel is analytic_ledger.ConfidenceLevel
    assert c.LIKELIHOOD_RANGES is analytic_ledger.LIKELIHOOD_RANGES
    assert set(c.LIKELIHOOD_LABELS) == set(c.LikelihoodTerm)
    assert set(c.CONFIDENCE_DEFINITIONS) == set(c.ConfidenceLevel)
    assert c.likelihood_phrase(c.LikelihoodTerm.LIKELY) == "Likely (55%–80%)"


@pytest.mark.parametrize(
    "enum, table",
    [
        (c.Tlp, c.TLP_DEFINITIONS),
        (c.Pap, c.PAP_DEFINITIONS),
        (c.SourceReliability, c.SOURCE_RELIABILITY_LABELS),
        (c.InformationCredibility, c.INFORMATION_CREDIBILITY_LABELS),
        (c.Severity, c.SEVERITY_DEFINITIONS),
        (c.ControlStatus, c.CONTROL_STATUS_DEFINITIONS),
        (c.ProvenanceClass, c.PROVENANCE_LABELS),
    ],
)
def test_every_term_is_defined(enum, table):
    assert set(table) == set(enum)
    assert all(text.strip() for text in table.values())


def test_tlp_is_version_2():
    assert [t.value for t in c.Tlp] == ["CLEAR", "GREEN", "AMBER", "AMBER+STRICT", "RED"]
    assert c.tlp_label(c.Tlp.AMBER_STRICT) == "TLP:AMBER+STRICT"
    with pytest.raises(ValueError):
        c.Tlp("WHITE")


@pytest.mark.parametrize(
    "scores, expected",
    [
        ((None, 2, 2), c.GapStatus.NOT_ASSESSED),
        ((0, 2, 2), c.GapStatus.CRITICAL),
        ((2, 0, 0), c.GapStatus.CRITICAL),
        ((2, 1, 0), c.GapStatus.MODERATE),
        ((1, 0, 1), c.GapStatus.MODERATE),
        ((1, 2, 0), c.GapStatus.MINOR),
        ((2, 0, 2), c.GapStatus.NONE),
        ((2, 2, 1), c.GapStatus.NONE),
    ],
)
def test_gap_status_follows_the_stated_rule(scores, expected):
    assert c.derive_gap_status(*scores) is expected


def test_gap_scores_outside_the_scale_are_rejected():
    with pytest.raises(ValueError, match="alerting"):
        c.derive_gap_status(2, 3, 0)


def test_report_ids():
    assert c.format_report_id("TAA", 2026, 7) == "PG-TAA-2026-0007"
    for bad in ("taa", "T", "TOOLONGX", "T-A"):
        with pytest.raises(ValueError):
            c.format_report_id(bad, 2026, 1)
    with pytest.raises(ValueError):
        c.format_report_id("TAA", 2026, 0)


def test_header_accepts_a_consistent_issue_and_normalises_to_utc():
    eastern = timezone(timedelta(hours=-5))
    header = _header(
        issued_at=NOW.astimezone(eastern),
        sources=(c.SourceCitation(name="crt.sh", reliability=c.SourceReliability.B, credibility=c.InformationCredibility.PROBABLY_TRUE),),
    )
    assert header.issued_at.tzinfo == timezone.utc
    assert header.marking == "TLP:AMBER · PAP:AMBER"
    assert header.sources[0].rating == "B2"


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"report_id": "GAP-2026-001"}, "does not match"),
        ({"issued_at": datetime(2026, 11, 26)}, "timezone"),
        ({"tlp": "WHITE"}, "tlp"),
        ({"version": 2}, "last revision"),
        ({"status": c.ReportStatus.FINAL}, "status"),
        ({"valid_until": date(2026, 1, 1)}, "valid_until"),
        ({"audience": ()}, "audience"),
        ({"surprise": "x"}, "surprise"),
    ],
)
def test_header_rejects_inconsistent_or_undefined_values(overrides, message):
    with pytest.raises(ValidationError, match=message):
        _header(**overrides)


def test_a_preview_is_an_unissued_draft():
    preview = _header(report_id=None, version=0, revision_history=())
    assert not preview.issued
    with pytest.raises(ValidationError, match="unissued preview"):
        _header(report_id=None, version=1)
    with pytest.raises(ValidationError, match="revision history"):
        _header(revision_history=())


def test_revision_history_must_be_contiguous():
    revisions = (
        c.Revision(version=1, issued_at=NOW, status=c.ReportStatus.DRAFT, summary="First"),
        c.Revision(version=3, issued_at=NOW, status=c.ReportStatus.FINAL, summary="Third"),
    )
    with pytest.raises(ValidationError, match="1..N"):
        _header(version=3, status=c.ReportStatus.FINAL, revision_history=revisions)


def test_judgments_carry_likelihood_and_confidence_separately():
    judgment = c.Judgment(
        statement="The cluster is operated by one actor.",
        likelihood=c.LikelihoodTerm.LIKELY,
        confidence=c.ConfidenceLevel.MODERATE,
        rationale="Shared certificate and registrar pattern.",
    )
    assert judgment.phrase() == "Likely (55%–80%); moderate confidence"
    with pytest.raises(ValidationError):
        c.Judgment(statement="x", likelihood="probable", confidence="moderate", rationale="y")
    with pytest.raises(ValidationError):
        c.Judgment(statement="x", likelihood="likely", rationale="y")


def test_defanging_applies_to_people_never_to_machines():
    url = "https://login.example.com/a.php"
    assert c.render_indicator(url, "url", c.OutputFormat.MARKDOWN) == "hxxps[:]//login[.]example[.]com/a[.]php"
    for machine in set(c.OutputFormat) - c.HUMAN_READABLE_FORMATS:
        assert c.render_indicator(url, "url", machine) == url
        assert c.render_indicator("192.0.2.10", "ipv4-addr", machine) == "192.0.2.10"


@pytest.mark.parametrize(
    "value, kind",
    [
        ("192.0.2.44", "ipv4-addr"),
        ("203.0.113.0/24", "ipv4-addr"),
        ("2001:db8::5", "ipv6-addr"),
        ("c2.example", "domain-name"),
        ("update.example.com", "domain-name"),
        ("hxxps[:]//cdn[.]example[.]net/x", "url"),
        ("ops@example.org", "email-addr"),
        ("d41d8cd98f00b204e9800998ecf8427e", "file:hashes.MD5"),
    ],
)
def test_reserved_examples_pass(value, kind):
    assert c.unreserved_indicator(value, kind) is None


@pytest.mark.parametrize(
    "value, kind",
    [
        ("8.8.8.8", "ipv4-addr"),
        ("10.0.0.5", "ipv4-addr"),
        ("2606:4700::1111", "ipv6-addr"),
        ("evil-corp.com", "domain-name"),
        ("example.com.attacker.net", "domain-name"),
        ("https://real-bank.com/login", "url"),
        ("hxxp[:]//45[.]9[.]148[.]1/a", "url"),
        ("someone@gmail.com", "email-addr"),
    ],
)
def test_real_or_private_examples_are_rejected(value, kind):
    assert c.unreserved_indicator(value, kind) == value


def test_text_scan_finds_unreserved_values_even_when_defanged():
    text = (
        "Beacon to 192.0.2.7 and 45[.]9[.]148[.]1, then hxxps[:]//cdn[.]real-host[.]io/p; "
        "mail from a@example.com; see contract.py and v1.5.0; 2001:db8::1 and 2606:4700::1111."
    )
    assert c.unreserved_values(text) == ["45.9.148.1", "2606:4700::1111", "cdn.real-host.io"]
