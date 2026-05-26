"""Static data assets bundled with adversary_pursuit.

@decision DEC-60-PIVOT-POLICY-003
@title Bundled top-1k allowlist ships as data/pivot_allowlist_top1k.txt; source is Cloudflare Radar
@status accepted
@rationale See pivot_policy.py module docstring for source URL, snapshot date, and SHA-256.
           Data directory is a Python package so pkg_resources / importlib.resources can
           locate the files without relying on filesystem path assumptions.
"""
