# Investigation Report

## Metadata

- **Workspace:** fixture-workspace
- **Date:** {DYNAMIC_DATE}
- **Total Score:** 300
- **Modules Used:** 1
- **Total Indicators:** 2

## Executive Summary

This investigation collected **2 indicator(s)** across **1 module(s)**. Total pursuit score: **300 pts**.
Indicator types: domain-name: 1, ipv4-addr: 1.

## Timeline

- `{DYNAMIC_TIMESTAMP}` — **osint/whois_lookup** on `evil.example.com` -> 2 object(s)

## Indicators of Compromise

| Type | Value | First Seen |
|------|-------|------------|
| ipv4-addr | 1.2.3.4 | unknown |
| domain-name | evil.example.com | unknown |

## Interview Notes

**Q: Why did you start this pursuit?**
A: Threat intel tip from partner

**Q: How did you find the first indicator?**
A: WHOIS lookup on suspicious domain

**Q: What is the single most important thing you learned?**
A: Infrastructure reuse across campaigns

**Q: How could someone interrupt this adversary's operation?**
A: Sinkhole the C2 domain

**Q: What is the next step?**
A: Pivot to related ASN block

## Analyst Notes

_No analyst notes._

## Statistics

- Total indicators: 2
- By type:
  - domain-name: 1
  - ipv4-addr: 1
- Total score: 300
