# Session status — what worked, what didn't, where we're stuck, what's next

Date: 2026-10-19. Covers the construction → pass@k hub pipeline work on branch
`pipeline-split-and-harbor-format-fixes` (latest commit `8e827b1`, pushed to origin). For the
architecture itself, see [HUB_PIPELINE_PLAN.md](HUB_PIPELINE_PLAN.md) — this doc is the
narrower "what happened this round" summary.

## 1. What worked

- **Construction, end to end.** `build_full_pipeline_task.py`'s `build_steps()` (~22 steps:
  inject vuln → boot/validate oracle+noop+negative-control → QC/harden loop → collect bundle)
  completed cleanly for both w-social and Dolibarr. Dolibarr's construction run produced a real,
  accepted task (`dolibarr-estate/invoice-listing-missing-authz`, CWE-862).
- **Splitting construction and pass@k into two separate hub tasks.** This was the main fix
  going into this session: one combined 112-step task (construction + 10 pentest branches,
  10-way concurrent VM sandbox deployment) reliably `TERMINATED` with no error surfaced by the
  hub. Splitting into two task publishes, with pass@k referencing construction's artifact by id,
  fixed this — confirmed by a 5-way-concurrency pass@k run completing cleanly end to end where
  two independent 10-way runs (one per app) both `TERMINATED`.
- **The new mechanism the split depends on**: `load_artifact`'s cross-task `artifact_id=` mode
  (as opposed to same-task `collected_artifacts_step_id`). This was explicitly smoke-tested in
  isolation (`ops/build_cross_task_artifact_smoketest.py`: task A collects a file tree, task B —
  a wholly separate publish — loads it by artifact id and confirms contents match) before being
  trusted in the real pipeline, and passed.
- **Root-causing the `TERMINATED` failures.** Traced through the installed `agentenv-framework`
  pip package source (not guessed): `RunStatus` in `agent_env/runner/runner.py` doesn't even
  define `TERMINATED` client-side, meaning it leaks from the hub's own execution engine.
  `agent_env/providers/sandbox_providers/modal_vm_sandbox.py` confirmed our `sandbox_mode: "vm"`
  deploys use Modal's **experimental** `vm_runtime` sandboxes, with no retry around sandbox
  *creation* itself — strong evidence 10-way concurrent creation calls exceeded Modal's capacity
  for this experimental resource. The follow-up 5-way-concurrency run completing cleanly
  empirically confirmed concurrency count (not total DAG size) is the real limit.
- **Root-causing the Dolibarr pass@5 "0% pass rate".** Rather than accepting the number at face
  value, pulled all 5 `boot-target-deepseek-{1..5}` trajectories via
  `mcp__...agentenvhub__get_trajectory_url` and read them. Found a deterministic, 5/5 refusal by
  the construction-model helper (Claude Sonnet 5): it inspected `/app/task`, recognized the
  Harbor eval scaffold, and correctly refused the instruction to patch
  `docker-compose.yaml`/`etc/hosts` as a verification-bypass pattern. Also independently
  confirmed (per explicit request, not assumed) why earlier runs this session hadn't hit this:
  those were scored via `judge-rubric`'s different code path (`docker compose exec` on the
  internal network), not the newer host-side `verify-{label}` step.
- **The verifier + boot-target fix itself** (code-complete, both halves consistent with each
  other): `audit_technique_check.py` now resolves `web` through `docker compose -p construction
  exec -T main` instead of a host-side `curl localhost:8080`; `boot_target`'s prompt in
  `build_full_pipeline_task.py` now only runs `docker compose up` — nothing an eval-aware model
  has reason to refuse.

## 2. What did NOT work / failed

- **10-way concurrent pass@k in one hub task** — `TERMINATED`, twice, independently (w-social
  and Dolibarr). Not retried at that concurrency; superseded by the split + lower per-task
  concurrency.
- **The original host-side verifier design** — structurally depended on `boot_target` doing
  something (expose a host port, edit `/etc/hosts`) that an eval-aware model reliably refuses.
  This made every pass@5 behavior-gate score read as "0%" regardless of whether the pentest
  model actually succeeded — a false negative, not a real difficulty signal.
- **A single-VM, N-parallel-trial pass@k design** (explored as a way to dodge the Modal
  concurrency ceiling entirely) — ruled out, not attempted. `install_agent`'s
  `container_name`/`a2a_port`/`agent_name` are independently overridable per call, so multiple
  agents on one VM is mechanically possible, but real pass@k isolation needs independent
  app/DB state per trial, which means re-engineering every task bundle's `docker-compose.yaml`
  to run N port-offset copies of the whole stack — construction-template work, not an ops-script
  change. Lower per-publish concurrency (already proven) was pursued instead.

## 3. Where we're stuck right now

- **The verifier fix cannot take effect on a real run yet.** `run_code` steps (including
  `verify-{label}`) execute a pre-registered `FileArtifact`
  (`script_artifact_id="audit-technique-check"`), not whatever is on disk in this repo. Editing
  `audit_technique_check.py` locally only changes what a future `FileArtifact.put()` *would*
  register — it does not update what the hub already has registered under that id.
  Registering/updating a `FileArtifact` requires a live `pymongo.MongoClient` connection
  directly to the hub's own MongoDB:
  - No REST endpoint exists for it (`GET /api/v1/docs/openapi` has no
    `POST /api/v1/artifacts` or equivalent).
  - No MCP tool exists for it either (`agentenvhub`'s MCP tools have `get_artifact`/
    `get_artifact_versions`, no `create_artifact`/`update_artifact`).
  - The Mongo connection's real coordinates aren't in this repo or in the installed
    `agentenv-framework` package.

  **Until someone with direct Mongo access (or a working `FileArtifact.put()` path from a
  different environment) pushes the updated script content, every `verify-{label}` score from a
  fresh pass@k run should be treated as suspect** — specifically, check the corresponding
  `boot-target-{label}` trajectory for a refusal/failure before trusting a 0% result.

- **w-social's pass@k run is still sitting at `TERMINATED`** (10-way concurrency), not yet
  relaunched at reduced concurrency. Construction itself completed and its artifact is reusable —
  no need to redo construction, just a fresh `build_passk_extension_task.py` publish at a lower
  `--attempts` count.

## 4. What needs to change next

1. **Find or get access to the hub's Mongo-backed `FileArtifact` store** (or whoever/whatever
   path originally registered `audit-technique-check`) and push the updated
   `audit_technique_check.py` content. This is the hard blocker — without it, the fix is inert.
2. **Once (1) is done, re-run pass@5 against the already-accepted Dolibarr construction
   artifact** (`full-pipeline-round-1-1792077214-construction-48303e1437d24b28`, sandbox
   `pipeline-vm-r1-1792077214`) to get a genuine (not refusal-contaminated) pass rate.
3. **Relaunch w-social's pass@k at 5-way (or lower) concurrency**, reusing its existing
   construction artifact rather than rebuilding it.
5. **Package the accepted Dolibarr bundle** via `ops/download_collected_bundle.py` into Harbor
   zip format — requested earlier this session, not yet done.
