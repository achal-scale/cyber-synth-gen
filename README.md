# cyber-synth-gen

Turns a (real app, vulnerability class) pair into a self-contained pentest environment in
[Harbor](https://github.com/laude-institute/harbor) format: a black-box web-security task an
agent solves in one sitting, graded by a deterministic verifier, not an LLM judge.

v1 scope is web-application vulnerabilities only (IDOR, SQLi, SSRF, XXE, traversal,
mass-assignment, business-logic, web-delivered RCE) — browser/kernel/DNS/IoT categories are a
later phase, not in this repo yet.

## The generation process, end to end

```
python3 pipeline-review/new_task.py <env> <vuln_type> <task_dir> [--cwe ...] [--cve ...]
    -> scaffolds task.toml, instruction_{L0,L1,L2}.md, environment/, solution/, tests/,
       trajectories/{oracle,noop,passk}/, unintended_findings.json
    -> YOU fill in the TODOs: inject the vulnerability, write solution/solve.sh, tests/test.sh
       (this is real engineering judgment per task — not scripted, see new_task.py's docstring
       for why)

python3 gate/contract_gate.py <task_dir> <rubric_pipeline_path>
python3 gate/oracle_noop_gate.py <task_dir>
python3 gate/sandbox_escape_gate.py <task_dir>
    -> all three must pass before anything else proceeds

python3 ops/launch_fleet.py <task_dir> --agent-cmd '<command that drives a model against the task>'
python3 gate/fleet_gate.py <task_dir>
python3 gate/stage2_gate.py <task_dir> <rubric_pipeline_path>

python3 ops/package_deliverable.py <task_dir> <rubric_pipeline_path> [--skip-fleet]
    -> re-runs every gate itself (does not trust that you ran them separately), and ONLY THEN
       zips task_dir into a deliverable with a MANIFEST.json recording every gate's verdict.
       Refuses to zip on any gate failure or missing required file. This is the actual
       "each task comes out as a zip with all required files" step.
```

**Input is exactly (env, vuln_type)**, per your requirement — `new_task.py`'s two required
positional args. Everything else (CWE, CVE, the actual vulnerability code, the exploit chain)
is filled in after scaffolding, not inferred from those two strings alone.

**There is a quality-check step**: three live-tested gates (contract, oracle/noop,
sandbox-escape) that must all pass, re-verified again at packaging time so a zip can't be
produced from a task that was gated once and then edited afterward.

**There is a pass@k step**: `ops/launch_fleet.py` runs each trial end to end (boot the task under
a unique Compose project, run the supplied `--agent-cmd` under its own deadline derived from
`[agent].timeout_sec`, stage and run the verifier as root, read the reward, tear down), writing
`trajectories/passk/<trial>/reward.txt`; `gate/fleet_gate.py` reads those files for v1's
single-model pass@5. Live-tested end to end against a real task (see CHANGELOG for the real
permission bug this caught and fixed). The one piece it does NOT supply is `--agent-cmd` itself
— the actual command that drives a model against a booted task — which is organization-specific
and passed in by the caller, not assumed or fabricated here.

## Where to work

| Work | Entry point |
| --- | --- |
| Scaffold a new task from (env, vuln_type) | [pipeline-review/new_task.py](pipeline-review/new_task.py) |
| Selecting a (app, vuln class) candidate | [sourcing/](sourcing/README.md) |
| Building the environment (construction loop) | [pipeline-review/](pipeline-review/README.md) |
| What the gates check | [gate/](gate/README.md) |
| What the fleet measures | [ops/launch_fleet.py](ops/launch_fleet.py) |
| Package a task into a deliverable zip | [ops/package_deliverable.py](ops/package_deliverable.py) |
| What QC grades (capability ladder, clustering, partial credit) | [environment-eval/](environment-eval/README.md) |

## Status — what's real vs. still missing

| Piece | State |
| --- | --- |
| `new_task.py` scaffold | Real, live-tested (correct files/dirs, correct task.toml substitution) |
| `gate/contract_gate.py` | Real, live-tested (pass and GATE-STOP paths both verified against `batch_01/dolibarr-B1-sqli`) |
| `gate/oracle_noop_gate.py` | Real, live-tested (pass and GATE-STOP paths both verified) |
| `gate/sandbox_escape_gate.py` | Real, live-tested (pass and GATE-STOP paths both verified; currently GATE-STOPs on every existing task in `batch_01`, since none are hardened yet — see CHANGELOG) |
| `gate/fleet_gate.py` | Real, live-tested (blocked and measured paths both verified against synthetic fixtures) |
| `ops/package_deliverable.py` | Real, live-tested (missing-path detection and zip/MANIFEST assembly both verified in isolation; full end-to-end run against a real task is blocked on no existing task yet clearing the sandbox-escape gate) |
| `ops/launch_fleet.py` | Real, live-tested (full real-container lifecycle verified end to end with a dummy `--agent-cmd`; kill-at-budget path verified via isolated mock test). Missing only the org's actual agent-harness invocation string, which is a caller-supplied argument by design, not something this script assumes |
| agent-env Task/Env graph wiring | **Local-only**: `agentenv_plugin/compose_env.py` registers a docker-compose env against a local agent-env CLI run. Real hub graphs are a separate, newer effort — see below |
| Automated candidate sourcing | Not started — hand-curated per `sourcing/README.md`'s rules |

## Hub pipeline (`ops/hub.py`, `ops/build_hub_task.py`) — status, 2026-10-06

A second, newer track: running this repo's tasks as real step-DAGs on the hosted
`agent-env-hub` (`agent-env-hub.internal.scale.com`), the way `dcueva-scale/synth-gen`'s
production pipeline does, instead of only locally via `ops/launch_fleet.py`.

**Proven real** (live-tested against the actual hub this session, not assumed from docs):
- Auth: `ops/hub.py`'s `mint()`/`call()` (AWS SigV4 STS → `s2sauth` JWT → hub REST). Confirmed
  with a real `GET /api/v1/tasks?project_id=...` returning 200.
- `deploy_agent(enable_docker=true)` gives real root Docker access inside the sandbox — not
  assumed from docs, confirmed by reading a real measurement (`rsi-probe-capabilities`, an
  artifact published by `synth-gen`'s own capability probe on 2026-08-27: `docker info`/`docker
  ps` both answered, uid 0).
- `ops/build_hub_task.py` generates a fleet-shaped step DAG (N legs × 5 steps: deploy → setup →
  pentest → collect → verify) from any of this repo's Harbor task bundles, and
  `cyber-synth-gen-dolibarr-idor-fleet` (3 legs, 15 steps) is published and live on the hub under
  project `6a97344cdf04bf9f053a4098` as proof.
- `ops/generate_from_sheet.py` is the general entry point on top of `build_hub_task.py`: a CSV
  of `env,vuln_type[,cwe,cve,ticket,attempts,tier,model]` rows, one row per task. A row whose
  `tasks_built/<env>-<vuln_type>/` doesn't exist (or is still mid-scaffold) is scaffolded via
  `pipeline-review/new_task.py` and reported `needs-manual-build` — vulnerability injection is
  real engineering judgment this script deliberately does not fake. A row that's already built
  gets its hub fleet DAG generated and (with `--publish`) published, same as `build_hub_task.py`
  alone. One bad/incomplete row never stops the rest of the sheet. Live-tested this session on a
  2-row sheet (one already-built row correctly produced its 15-step DAG, one new `(env,
  vuln_type)` pair was correctly scaffolded with TODOs rather than faked).

**Blocked, with stand-ins in place** (see `ops/build_hub_task.py`'s module docstring for the
exact swap-over): the per-leg `setup` and `verify` steps should be a deterministic `run_code`
step and a deterministic `env_outcome_verifier` step, respectively — both require registering a
`FileArtifact`, which requires a live `pymongo.MongoClient` connection to the hub's own
MongoDB (confirmed by reading `agent_env.artifact.artifacts.file.FileArtifact.put()`'s source,
from the public `agentenv-framework` PyPI package — `pip install agentenv-framework`, import
`agent_env`). That connection's real coordinates (a `.agentenv/config.toml` with a
`[stores.document]` Mongo URI, or whatever `AGENT_ENV_CONFIG` resolves to) are not in this repo,
not in `agentenv-framework`, and not reproduced by any REST endpoint in the hub's own OpenAPI
spec (`GET /api/v1/docs/openapi` was fetched and read in full: no `POST /api/v1/artifacts`
exists, only per-purpose routes like `file-artifact-universes/*` and `publish-json`, none of
which create a generic `FileArtifact`). Until that config is available, the published fleet
task's `setup` step is a second `prompt_agent` turn (the setup is visible to the agent, not a
silent pre-boot) and its `verify` step is an `agent_prompt_response_verifier` rubric (LLM-judge
against the agent's final text, not an exact per-boot-marker match) — real steps, weaker
guarantees than the local `tests/test.sh` pipeline, never run yet end-to-end.

## Roles

- **Builder** (this pipeline, run by whoever is authoring a task): selects, injects, builds, and
  self-verifies oracle=1/noop=0 before handing off.
- **Reviewer**: independent pass over a built task before it ships. Not automated in v1 — a
  person or a separate agent, not the builder re-checking their own work.
- **Attempter**: the fleet model(s) that actually solve the task for difficulty measurement.
  v1 runs exactly one model (DeepSeek V4-Flash) at pass@5. Mid-tier and frontier stages are a
  later phase.
