# The construction loop

One (app, vuln class) candidate in; one Harbor environment out, with its oracle/noop
verification, sandbox-hardening log, and a single model's pass@5 result against it.

## The stages

```
candidate row (sourcing/CANDIDATES.csv)
   │
   ▼
[select]   confirm the candidate against sourcing's eligibility rules; for a CVE candidate,
           live-verify it via web search before trusting the attribution
   │
   ▼
[inject]   reintroduce the real CVE against its documented version, or organically weaken one
           real production code path (never a bolted-on synthetic endpoint)
   │
   ▼
[build]    environment/ (Dockerfile(s), docker-compose.yaml, vendored release tarballs +
           sha256 checks, digest-pinned base images, gateway that mints a fresh per-boot
           verifier token), task.toml, instruction_{L0,L1,L2}.md, solution/solve.sh,
           tests/test.sh, unintended_findings.json
   │
   ▼
[gate]     contract gate -> oracle/noop gate -> sandbox-escape gate  (see ../gate/README.md)
   │
   ▼
[handoff]  reviewer takes it from here — not automated, not the builder re-checking their own
           work (see root README's Roles section)
   │
   ▼  (after review passes)
[fleet]    ../ops/launch_fleet.py — single model, pass@5 (v1 scope)
```

## What's different from synth-gen's construction loop here

- synth-gen's hardest isolation rule is "the builder never sees the paper," because the risk is
  source leakage into the bundle. We have no equivalent leakage risk — the risk instead is
  **a non-unique solve path or a sandbox that doesn't actually contain the agent**, so our extra
  gate is sandbox-escape, which synth-gen has no equivalent of at all.
- synth-gen's review stage repairs the bundle and replays a baseline in the same construction
  loop. Ours hands off to an independent reviewer instead (per your decision: builder creates,
  reviewer and attempter are separate roles, not simulated by the builder in v1).

## Status

Documented, not yet wired as an agent-env Task graph. The stage boundaries above match what we
already do by hand for every task in `cyber-sample-tasks/batch_01` — this README is the written
contract; `build.py`-equivalent graph generation is a later phase.
