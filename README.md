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
| agent-env Task/Env graph wiring | Not started — everything above runs as standalone scripts, not yet an agent-env DAG |
| Automated candidate sourcing | Not started — hand-curated per `sourcing/README.md`'s rules |

## Roles

- **Builder** (this pipeline, run by whoever is authoring a task): selects, injects, builds, and
  self-verifies oracle=1/noop=0 before handing off.
- **Reviewer**: independent pass over a built task before it ships. Not automated in v1 — a
  person or a separate agent, not the builder re-checking their own work.
- **Attempter**: the fleet model(s) that actually solve the task for difficulty measurement.
  v1 runs exactly one model (DeepSeek V4-Flash) at pass@5. Mid-tier and frontier stages are a
  later phase.
