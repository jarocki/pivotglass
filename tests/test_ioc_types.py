"""Tests for IoC type detection (Phase 17R).

@decision DEC-IOC-TYPES-001 — see core/ioc_types.py for rationale.
"""

from __future__ import annotations

from adversary_pursuit.core.ioc_types import detect_ioc_type


class TestDetectIocType:
    """Unit tests for detect_ioc_type()."""

    # --- IPv4 ---
    def test_ipv4_simple(self):
        assert detect_ioc_type("8.8.8.8") == "ipv4"

    def test_ipv4_with_leading_zero_octets(self):
        assert detect_ioc_type("192.168.001.001") == "ipv4"

    def test_ipv4_max_values(self):
        assert detect_ioc_type("255.255.255.255") == "ipv4"

    def test_ipv4_min_values(self):
        assert detect_ioc_type("0.0.0.0") == "ipv4"

    def test_ipv4_invalid_octet_999(self):
        assert detect_ioc_type("999.0.0.1") is None

    def test_ipv4_invalid_too_few_octets(self):
        assert detect_ioc_type("1.2.3") is None

    def test_ipv4_invalid_non_numeric(self):
        # "abc.def.ghi.jkl" looks like a domain (valid FQDN pattern) — not None
        # Use something with clearly invalid characters for a non-ipv4, non-domain test
        assert detect_ioc_type("300.0.0.1") is None

    # --- IPv6 ---
    def test_ipv6_loopback(self):
        assert detect_ioc_type("::1") == "ipv6"

    def test_ipv6_full(self):
        assert detect_ioc_type("2001:db8::1") == "ipv6"

    def test_ipv6_full_expanded(self):
        assert detect_ioc_type("2001:0db8:0000:0000:0000:0000:0000:0001") == "ipv6"

    # --- Domain ---
    def test_domain_simple(self):
        assert detect_ioc_type("example.com") == "domain"

    def test_domain_subdomain(self):
        assert detect_ioc_type("sub.example.co.uk") == "domain"

    def test_domain_deep_subdomain(self):
        assert detect_ioc_type("a.b.c.example.com") == "domain"

    def test_domain_invalid_no_tld(self):
        assert detect_ioc_type("localhostonly") is None

    # --- URL ---
    def test_url_http(self):
        assert detect_ioc_type("http://example.com") == "url"

    def test_url_https(self):
        assert detect_ioc_type("https://evil.example.com/path?q=1") == "url"

    def test_url_with_ip(self):
        assert detect_ioc_type("http://8.8.8.8/malware") == "url"

    # --- MD5 ---
    def test_md5_valid(self):
        assert detect_ioc_type("d41d8cd98f00b204e9800998ecf8427e") == "md5"

    def test_md5_uppercase(self):
        assert detect_ioc_type("D41D8CD98F00B204E9800998ECF8427E") == "md5"

    def test_md5_wrong_length(self):
        # 31 chars — not MD5
        assert detect_ioc_type("d41d8cd98f00b204e9800998ecf842") is None

    # --- SHA1 ---
    def test_sha1_valid(self):
        assert detect_ioc_type("da39a3ee5e6b4b0d3255bfef95601890afd80709") == "sha1"

    def test_sha1_uppercase(self):
        assert detect_ioc_type("DA39A3EE5E6B4B0D3255BFEF95601890AFD80709") == "sha1"

    # --- SHA256 ---
    def test_sha256_valid(self):
        assert (
            detect_ioc_type("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
            == "sha256"
        )

    def test_sha256_detected_over_sha1_length(self):
        # 64 hex chars → sha256, not sha1
        val = "a" * 64
        assert detect_ioc_type(val) == "sha256"

    # --- Email ---
    def test_email_simple(self):
        assert detect_ioc_type("user@example.com") == "email"

    def test_email_subdomain(self):
        assert detect_ioc_type("admin@mail.example.co.uk") == "email"

    def test_email_no_at_sign(self):
        assert detect_ioc_type("notanemail.com") != "email"

    # --- Edge cases ---
    def test_empty_string(self):
        assert detect_ioc_type("") is None

    def test_whitespace_only(self):
        assert detect_ioc_type("   ") is None

    def test_whitespace_stripped_before_check(self):
        assert detect_ioc_type("  8.8.8.8  ") == "ipv4"

    def test_garbage_string(self):
        assert detect_ioc_type("not-an-ioc!!!") is None

    def test_sha256_before_sha1(self):
        """64-char hex must be sha256, not sha1 or md5."""
        val = "b" * 64
        assert detect_ioc_type(val) == "sha256"

    def test_sha1_before_md5(self):
        """40-char hex must be sha1, not md5."""
        val = "c" * 40
        assert detect_ioc_type(val) == "sha1"

    def test_md5_is_32_chars(self):
        """32-char hex is md5."""
        val = "d" * 32
        assert detect_ioc_type(val) == "md5"
