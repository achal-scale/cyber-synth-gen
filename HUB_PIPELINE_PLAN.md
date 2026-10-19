# Hub pipeline — how it works, what's blocked, what failed

Status date: 2026-10-19. This replaces the 2026-10-06 planning doc of the same name — that
doc's §4/§5 plan (merge services into one `deploy_env` image) was **not** the path actually
taken. We ended up on §5's "not pursuing right now" option instead: `deploy_sandbox` (one VM,
human/script-initiated, not agent-initiated) + `install_agent` host mode, run directly via
`ops/hub.py`'s REST client from this machine — which sidesteps the "no agent-initiated
deploy_sandbox/run_docker_container" platform restriction because the *agent* never calls
`run_task`, we do.

## 1. The current architecture

Two separate hub tasks per round, driven by `ops/drive_full_pipeline.py`, not one combined DAG:

```
drive_full_pipeline.py
 ├─ 1. build + publish + run_task  CONSTRUCTION task  (build_full_pipeline_task.py, build_steps())
 │     one VM sandbox, one construction agent (anthropic/claude-sonnet-5):
 │     inject vuln → boot/validate (oracle+noop+negative-control) → QC/harden loop → collect bundle
 │     ~22 steps, ends in a `collect-task-bundle` step producing a FileArtifactUniverse id
 │
 ├─ 2. read that artifact id out of the completed run's result.metadata
 │
 ├─ 3. build + publish + run_task  PASS@K task  (build_passk_extension_task.py, build_steps())
 │     N fully independent attempt-branches, each its OWN fresh VM sandbox:
 │       deploy_sandbox → install_agent (host mode) → load_artifact(artifact_id=<construction's>)
 │       → boot_target (prompt_agent, patches nothing but `docker compose up`)
 │       → pentest (prompt_agent, the model under test, max_turns=100)
 │       → collect → verify (run_code, audit_technique_check.py) → judge (rubric, docker exec)
 │     no attempt depends on any other, so all N run concurrently
 │
 └─ 4. read verify-{label} scores, compute pass@k rate, accept (≤30% tolerance) or
       harden-and-loop (fold a hardening note into next round's vuln-spec)
```

### Why split into two hub tasks instead of one

A single combined task (construction + 10 pentest-attempt branches, 112 steps, 10-way
concurrent sandbox deployment) reliably ends in `TERMINATED` with **no error surfaced by the
hub** — confirmed by two independent runs this session (w-social and Dolibarr, both at 10-way
concurrency). Root cause (confirmed via the installed `agentenv-framework` pip package source,
`agent_env/providers/sandbox_providers/modal_vm_sandbox.py`): our `sandbox_mode: "vm"` deploys
use Modal's **experimental** `vm_runtime: True` sandboxes (full nested Docker-in-VM). The
code's own comment notes Modal's client retries `RESOURCE_EXHAUSTED` internally for load, but
there's no retry around sandbox *creation* itself — 10 concurrent `_experimental_create.aio()`
calls exceeds this experimental resource's capacity, and the hub's orchestration layer aborts
the whole task rather than cleanly failing one branch. A follow-up run at **5-way** concurrency
(same task shape, same step count per branch) completed cleanly end to end — concurrency count,
not total DAG size, is the real limit. This is also a practical benefit, not just a workaround:
splitting means construction's own ~22 steps can be re-used (via `--task-bundle-artifact-id`)
across as many separate pass@k task publishes as needed (5+5, 5+5+5, ...) without re-running
construction, and a failed pass@k run doesn't require re-running construction either.

**New mechanism this split depends on, smoke-tested separately** (`load_artifact`'s
`artifact_id=` cross-task mode, not just its same-task `collected_artifacts_step_id` mode):
`ops/build_cross_task_artifact_smoketest.py` publishes two independent hub tasks — task A
writes a small nested file tree and collects it; task B, a *separate* task publish, loads task
A's real collected artifact id via `load_artifact(artifact_id=...)` and confirms the files
landed with correct content. This is the one piece of the split design that isn't already
covered by the long construction+pass@k runs (those exercise the same-task
`collected_artifacts_step_id` mode); run it before trusting any new environment/account's
cross-task artifact behavior.

### Key files

| File | Role |
| --- | --- |
| `ops/drive_full_pipeline.py` | Outer driver: publishes/runs both tasks per round, reads results, accept/harden decision, multi-round loop |
| `ops/build_full_pipeline_task.py` | Construction task DAG builder (`build_steps`) + shared helpers (`_isolated_pentest_branch`, `_verify_step_real`, `_judge_rubric_step`, `_final_bundle_step`) reused by the pass@k builder |
| `ops/build_passk_extension_task.py` | Pass@k task DAG builder: N independent attempt-branches referencing construction's artifact by id |
| `ops/hub.py` | Raw REST client: AWS SigV4 STS → `s2sauth` JWT → `agent-env-hub` API (`publish_task`, `run_task`, `run_status`) |
| `ops/verify_scripts/audit_technique_check.py` | The real behavior-gate verifier script (registered hub-side as the `audit-technique-check` FileArtifact, see §3) |
| `ops/download_collected_bundle.py` | Pulls a completed `collect_artifacts` step's files down via `aws s3 cp` and zips them into Harbor layout |
| `ops/resume_hardening_loop.py` | Resumes an in-flight round if the local driver process died without affecting the hub-side run |
| `ops/build_cross_task_artifact_smoketest.py` | One-off smoke test proving cross-task `load_artifact(artifact_id=...)` works (see above) |
| `ops/construction_step*.md` | The construction agent's per-turn prompts (1a–1g inject, 2a–2d boot/validate, 3a–3d QC/harden loop) |

## 2. Real finding this session: the pass@5 "0%" result was not genuine

A real Dolibarr pass@5 run (construction accepted, task `dolibarr-estate/invoice-listing-
missing-authz`, CWE-862) scored **0/5 on the behavior gate** against DeepSeek-V4-Flash. That
looked like "DeepSeek couldn't find the IDOR," but trajectory inspection of all 5
`boot-target-deepseek-{1..5}` steps showed the real cause: **the construction-model helper
(Claude Sonnet 5) refused the same instruction in all 5 attempts.** It inspected `/app/task`,
recognized the Harbor eval scaffold (`task.toml`, `instruction_L*.md`, `tests/isolation_test.sh`,
`unintended_findings.json`), and correctly treated "patch docker-compose.yaml to expose a host
port + edit /etc/hosts" as a verification-bypass/prompt-injection pattern — a deterministic 5/5
refusal, not a fluke. Because the port was never exposed on the host, the verifier's old
host-side `curl http://localhost:8080/...` failed with `rc=7` (connection refused) identically
every time.

This did **not** affect earlier runs' pass@k scores this session, because those were read from a
different step: `judge-rubric-{label}` runs `tests/test.sh` via
`docker compose -p construction exec -T main bash -c "..."` — resolving `web` over `main`'s own
**internal** Docker network, never the VM host's `localhost`. The host-port dependency was
unique to the newer `verify-{label}` (`run_code`/`audit_technique_check.py`) step added later
this session, which hadn't been exercised against this exact refusal mode before.

**Fix applied** (both halves, confirmed consistent with each other):
- `ops/verify_scripts/audit_technique_check.py`: the verifier's HTTP check now goes through
  `docker compose -p construction exec -T main curl ... http://web:8080/...` — the same
  resolution path `judge-rubric` already uses successfully — instead of a host-side
  `curl http://localhost:8080`.
- `ops/build_full_pipeline_task.py`'s `boot_target` prompt: dropped the docker-compose
  ports-patch and `/etc/hosts`-edit instructions entirely; it now only runs
  `docker compose -p construction up -d --build --wait`, which an eval-aware model has no
  reason to refuse.

## 3. The fix is deployed: `FileArtifact.put()` is real and reachable, not blocked

Earlier in this project it looked like registering/updating a `FileArtifact` needed direct
`pymongo.MongoClient` access to the hub's own MongoDB that no REST endpoint or MCP tool exposes
— true as far as it goes, but there turns out to be a real path anyway: **`agentenvhub-sdk`**
(already a dependency of this repo's venv) ships exactly that missing config. Importing
`agentenvhub_sdk.bootstrap` points `AGENT_ENV_CONFIG` at its bundled `config.prod.toml`, which
wires `[stores.document]` to a real `MongoDocumentStore` (URI/db name resolved from AWS Secrets
Manager secret `team/frontier-data/agent-env`) and `[stores.object]` to a real S3-backed store —
both authenticated via the same default AWS credential chain `ops/hub.py`'s `mint()` already
uses. `agent_env/artifact/artifacts/file.py`'s `FileArtifact.put()` is fully implemented against
that config, not a stub.

`ArtifactStore.get()`'s own docstring confirms "Returns latest version if version not
specified," and `_verify_step_real` references `"audit-technique-check"` with no version pinned
— so registering a new version is sufficient; no change to `build_full_pipeline_task.py` is
needed for the next `verify-{label}` run to pick it up.

**To deploy the already-made fix**, with a fresh (not expired — STS session tokens are
short-lived) AWS session active:
```bash
.venv/bin/python3 -c "
import agentenvhub_sdk.bootstrap
from agent_env.artifact import FileArtifact
artifact = FileArtifact.put(
    id='audit-technique-check',
    description=\"Resolve web over main's internal docker network via docker compose exec, not a host port mapping\",
    file_path='ops/verify_scripts/audit_technique_check.py',
)
print('registered', artifact.id, 'version', artifact.version, artifact.object_url)
"
```
**Done this session**: `audit-technique-check` version 2 is now registered
(`s3://frontier-data-environments/artifacts/file/audit-technique-check/2/audit_technique_check.py`).
The next `verify-{label}` step on any fresh pass@k run will resolve this version automatically.

Any `verify-{label}` score recorded *before* this registration (i.e. the original Dolibarr
pass@5 0% result) should still be treated as **not a genuine difficulty signal** — it was scored
against version 1's host-side curl, which every `boot-target` refused. Re-run pass@k to get a
genuine reading.

## 4. Other known failure modes / status

- **w-social's pass@k run**: `TERMINATED` at 10-way concurrency, not yet relaunched at reduced
  (5-way) concurrency. Construction itself completed and is reusable via its own artifact id —
  no need to re-run construction, only a fresh `build_passk_extension_task.py` publish at lower
  `--attempts` (or multiple smaller publishes).
- **Single-VM, N-parallel-trial pass@k** (explored, not pursued): `install_agent`'s
  `container_name`/`a2a_port`/`agent_name` are independently overridable per call (the only hard
  restriction is no two steps sharing one `agent_name`), so multiple agents on one VM at
  different ports is mechanically possible. But real pass@k isolation needs independent
  app/DB state per trial, which means re-engineering each task bundle's `docker-compose.yaml`
  to run N port-offset copies of the whole stack on one VM — construction-template work, not an
  ops-script change. Lower per-task-publish concurrency (already proven to work) was pursued
  first instead.
- **MCP `get_run_status`** only tracks runs started via its own `run_task` tool call, not runs
  launched via `hub.py`'s direct REST client (which is how every script in this repo runs
  things) — always use `hub.run_status()` / `drive_full_pipeline.py`'s own polling for this
  project's runs, not that MCP tool.

## 5. Roles (unchanged from the original plan)

- **Builder**: the construction agent + `drive_full_pipeline.py`'s accept/harden loop.
- **Reviewer**: independent pass over a built/accepted task before it ships — not automated.
- **Attempter**: the pass@k model(s) under test. Current runs use DeepSeek-V4-Flash only.
