# Candidate selection

Fetches candidate (real app, vulnerability class) pairs and writes `CANDIDATES.csv`. v1 is a
curated list, not an automated fetcher — there is no arXiv-equivalent feed of "apps with
injectable vulnerabilities" to scrape. Candidates come from two sources:

1. **CWE-coverage gaps in what we've already shipped.** SSRF, XXE, broken function-level
   authorization, and web-delivered RCE each have exactly one task today — a second task per
   thin cluster is a standing candidate.
2. **Real, unpatched-version CVEs** in actively-maintained open-source web apps, verified via a
   live web search before being treated as fact (never fabricated — a false CVE attribution was
   caught and fixed in an earlier batch this way).

## Screening rules, in brief

A candidate is eligible when:

- It is a single, well-defined vulnerability class (CWE), not a vague "find something."
- It has exactly one correct attack path — no bolted-on synthetic endpoint, no alternate route
  that a model could stumble into and get credit for the wrong reason.
- The vulnerable code path is either (a) a real historical CVE reintroduced against its
  documented version, or (b) an organic weakening of one real production code path in the
  unmodified app — never a bespoke endpoint invented to host the bug.
- A safe/parameterized sibling of the same feature exists where plausible, as a deliberate decoy
  that must independently verify as a dead end (this is what `unintended_findings.json`
  documents downstream).

## CANDIDATES.csv columns

`app, app_version, cwe, cve (or "organic"), vuln_kind, requires_gpu (always false for v1),
notes`

## Status

Stub. No `fetch.py`/`screen.py` exist yet — candidates are currently hand-curated against the
rules above. Automating screening is a later phase, not a v1 requirement.
