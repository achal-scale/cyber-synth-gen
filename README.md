# cyber-synth-gen

Turns a (real app, vulnerability class) pair into a self-contained pentest environment in
[Harbor](https://github.com/laude-institute/harbor) format: a black-box web-security task an
agent solves in one sitting, graded by a deterministic verifier, not an LLM judge.

A multi-stage pipeline builds the environment and its gateway/verifier; a single model runs
pass@5 against it; gate checks (contract, oracle/noop, sandbox-escape, fleet) decide whether it
ships. v1 scope is web-application vulnerabilities only (IDOR, SQLi, SSRF, XXE, traversal,
mass-assignment, business-logic, web-delivered RCE) — browser/kernel/DNS/IoT categories are a
later phase, not in this repo yet.

This repo's shape follows the same pipeline pattern as `synth-gen` (arXiv paper → RSI
environment), adapted to a different domain and a different #1 concern: synth-gen's hardest
requirement is that the builder never sees the paper so the bundle can't leak the source;
ours is that the sandbox itself cannot be escaped, since these tasks hand an agent real exploit
capability.

## Where to work

| Work | Entry point |
| --- | --- |
| Selecting a (app, vuln class) candidate | [sourcing/](sourcing/README.md) |
| Building the environment | [pipeline-review/](pipeline-review/README.md) |
| What the gates check | [gate/](gate/README.md) |
| What the fleet measures | [ops/launch_fleet.py](ops/launch_fleet.py) |
| What QC grades (capability ladder, clustering, partial credit) | [environment-eval/](environment-eval/README.md) |

## Status

v1, just scaffolded. Construction-loop mechanics and gate logic are real; the agent-env Task/Env
graph wiring that actually runs this on a sandbox is not yet built — see each directory's README
for what's implemented vs. still a stub.

## Roles

- **Builder** (this pipeline, run by whoever is authoring a task): selects, injects, builds, and
  self-verifies oracle=1/noop=0 before handing off.
- **Reviewer**: independent pass over a built task before it ships. Not automated in v1 — a
  person or a separate agent, not the builder re-checking their own work.
- **Attempter**: the fleet model(s) that actually solve the task for difficulty measurement.
  v1 runs exactly one model (DeepSeek V4-Flash) at pass@5. Mid-tier and frontier stages are a
  later phase.
