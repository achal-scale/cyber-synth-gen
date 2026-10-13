# Hub pipeline — what we need to build

Scope: running `cyber-synth-gen`'s pentest tasks as real step-DAGs on the hosted
`agent-env-hub` (`agent-env-hub.internal.scale.com`), the way `dcueva-scale/synth-gen`'s
production RSI pipeline does, instead of only locally via `ops/launch_fleet.py` +
`blackbox-pentest-pass1`. This document is project-specific: it does not re-explain the
platform in general, only what *our* pentest-range shape needs and where each piece
currently stands.

Status date: 2026-10-06, end of the investigation session that produced this doc.

## 1. What's already proven, real, and reusable

- **Auth** (`ops/hub.py`): AWS SigV4 STS GetCallerIdentity → `s2sauth.internal.scale.com/jwt`
  → `x-jwt-assertion: JWT <token>` header on every `agent-env-hub.internal.scale.com/api/v1/*`
  call. Confirmed live (`GET /api/v1/tasks?project_id=...` → 200, full `GET
  /api/v1/docs/openapi` spec fetched and read). Uses the default AWS SSO session; no extra
  credential needed beyond what the user's AWS role already grants.
- **`agentenvhub-sdk` is installable and working**, contrary to earlier assumption. It's in
  Scale's private CodeArtifact registry (`scale-pypi`), not public PyPI — that's the whole
  reason it looked unreachable at first. Install:
  ```
  aws codeartifact login --tool pip --domain scale --domain-owner 307185671274 \
      --repository scale-pypi --region us-west-2
  pip install agentenvhub-sdk
  ```
  Gated by the same AWS role already in use (`production-developer` / account
  `307185671274`) — confirmed working with this project's own AWS session, no separate
  credential.
- **Real artifact creation now works**, unblocking everything that needed it:
  ```python
  import agentenvhub_sdk.bootstrap as hub_bootstrap
  hub_bootstrap.use_stage("prod")
  from agent_env.artifact import FileArtifact, DockerImageArtifact
  from agent_env.env.envs.website import WebsiteEnv
  ```
  `FileArtifact.put()`, `DockerImageArtifact.put()` (builds from a local image, pushes to
  ECR, registers), and `Env.put()` (e.g. `WebsiteEnv.put()`) were all exercised live this
  session and confirmed visible through the hub's own `get_artifact`/`get_task` API
  afterward — not just a local write.
- **`ops/hub.py`'s `publish_task()`** (raw `POST /api/v1/tasks`) works for *any* step type the
  platform defines, unlike the MCP `create_task` tool, which enforces its own narrower
  allowlist at *authoring* time. Use `ops/hub.py` directly when a step type isn't on that
  list; MCP's own tools are fine for anything that is.
- **`ops/build_hub_task.py`** generates a fleet-shaped step DAG (N legs, each a block of
  steps) from one of this repo's Harbor task bundles. Currently wired for the (now known to
  be wrong — see §2) dind architecture; needs the rewrite in §4.
- **`ops/generate_from_sheet.py`** — the general, CSV-driven entry point on top of
  `build_hub_task.py`. Takes `env,vuln_type[,cwe,cve,ticket,attempts,tier,model]` rows, one
  row per task: scaffolds via `pipeline-review/new_task.py` if not yet built, or generates +
  publishes the hub fleet DAG if it is. This part of the design does not change regardless of
  which environment architecture §4 lands on — only what `build_hub_task.py` generates
  per-leg changes.

## 2. What's dead-ended, and why (do not re-attempt these without new evidence)

- **`deploy_agent(sandbox_type="modal_vm", enable_docker=true)`** (Docker-in-Docker inside
  one agent's own sandbox). Empirically failed in a real run: `waiting for rootless docker
  daemon... did not become ready`, with TUN/TAP device creation and iptables kernel-module
  permission denials. This contradicts an earlier-read measurement
  (`rsi-probe-capabilities`, 2026-08-27) that showed the same combination working — that
  measurement is either stale, or was on a materially different sandbox configuration we
  haven't identified. Either way, do not depend on this path without a fresh, successful
  measurement first.
- **`deploy_sandbox` + `run_docker_container`** (one bare VM, N containers wired by Docker
  network, the *actual* pattern Scale's own FD-1812 pentest ranges use in production). This
  is the architecturally correct answer, and it is NOT technically broken — but both the MCP
  `create_task`/`run_task` tools AND the raw REST `run_task` endpoint explicitly refuse these
  two step types with "not permitted for agent-initiated runs." This is a deliberate platform
  policy keyed on *who* initiates the run, not a bug to route around. **A human, running the
  task themselves (hub UI or CLI, not through an agent), does not hit this restriction** — see
  §5 for what that means for us.
- **`deploy_env(type="website")`** as a drop-in multi-container primitive. Not blocked, but
  structurally the wrong tool: it provisions a whole bundled stack (`servicedb`, `db-mcp`,
  `website-browser`, `pgweb`, plus our two images) under a `gateway_mode="performance"`
  wrapper clearly designed for website-testing-with-browser-automation scenarios, not a
  generic "run N arbitrary containers" primitive. A live test failed immediately (our plain
  `nginx:alpine` backend container exited code 255, presumably failing whatever startup
  contract this harness expects of a "backend" image). It also confirmed the real internal
  hostname convention is `<env_id>-website-backend` / `<env_id>-website-frontend` (long,
  prefixed), not a bare service name — so even a working version of this path would still
  require rewriting every gateway's hardcoded `http://web:8080`-style hostnames.

## 3. The actual constraint this leaves us with

For anything **I (an agent) drive on the user's behalf**, the only step types available are
the MCP/REST-enforced allowlist:

```
agent_prompt_response_verifier, aggregate_verifiers, collect_artifacts, deploy_agent,
deploy_env, env_outcome_verifier, load_artifact, prompt_agent, reset_env, rubrics_verifier,
snapshot_agent_state, snapshot_env, verify_sandbox
```

None of our existing tasks' environments (3 services: db + appserver + gateway, wired by a
private Docker network, sharing volumes for the canary marker and verifier token) fit
natively into `deploy_env`'s single/dual-image Env types. Squeezing them in is real,
per-task engineering work, not a generic adapter — see §4.

## 4. What needs to be built, step by step (the actual task list)

### 4.1 Per-task environment rework (the big one — repeat per task we want on the hub)

For each task (starting with `dolibarr-idor` as the reference):

1. **Merge two of the three env services into one Docker image.** For `dolibarr-idor`:
   combine `db` (mariadb) + `appserver` (dolibarr/php) into one "backend" image via a
   startup script that launches `mysqld` in the background, waits for it, then runs the
   existing dolibarr entrypoint logic in the foreground. This eliminates the one
   cross-container dependency `db`↔`appserver` currently has (none — they don't share a
   volume today, only a network, so merging them into one container is low-risk).
2. **Keep `gateway` as the second ("frontend") image**, mostly unchanged.
3. **Rewrite the marker/credential handoff.** Today, `appserver`'s entrypoint writes
   `/canary/marker` + `/canary/creds.json` to a volume the `gateway` container also mounts;
   `gateway/setup.py` polls that file. `WebsiteEnv` (and any Env-type path) gives two
   containers with network connectivity but **no shared volume** between them. Replace the
   file-based handoff with a network call: either (a) the merged backend image serves the
   marker/creds over a small internal HTTP endpoint at boot, and `gateway/setup.py` polls
   *that* instead of a local file, or (b) invert the flow — have the gateway generate the
   marker itself (same as it already does for its own `verifier_token`) and push it into the
   backend over the network at backend-boot time. Pick (a) for `dolibarr-idor` first (smaller
   diff from the existing entrypoint-wrapper.sh); evaluate (b) if (a) turns out to fight the
   existing app's seeding assumptions.
4. **Confirm `WebsiteEnv`'s actual internal hostname** before wiring the gateway's `GLPI_BASE`
   / `DOLI_DB_HOST`-equivalent config to it — we know it's `<env_id>-website-backend`, not
   `backend`, but haven't yet confirmed whether that's resolvable as a bare hostname or needs
   a domain suffix. One cheap `prompt_agent` smoke step (`cat /etc/hosts`, `curl` both forms)
   before wiring the real task settles this for good.
5. **Build + push both images locally**, register via `DockerImageArtifact.put()`, register
   the `WebsiteEnv` via `Env.put()`. (Mechanically identical to the smoke test already run
   this session — see `ops/hub.py` usage in the session transcript / git history for the
   exact calls, or re-derive from §1's code snippet.)
6. **Fix the merged backend's own healthcheck/startup** so `run_docker_container`'s (or
   `deploy_env`'s) readiness check passes — this is almost certainly what made the smoke
   test's plain nginx image exit 255; a real backend image needs to match whatever this
   harness probes for (likely a specific port/health path convention — confirm empirically,
   don't guess twice).

### 4.2 Rewrite `ops/build_hub_task.py`'s step generation (once 4.1 lands for ≥1 task)

Replace the current dind-based `_deploy_step`/`_setup_step` with:

- `deploy_env(env_id=<task's registered WebsiteEnv>)` instead of `deploy_agent(enable_docker=true)`.
- `deploy_agent(env_ids=[<same env_id>])` for the actual pentest agent (not
  `sandbox_name`-sharing — that pattern is the deploy_sandbox one, which we can't use).
- Drop `_setup_step` entirely — the environment boots itself via `deploy_env`, no
  `prompt_agent`-as-setup stand-in needed anymore. This closes the fidelity gap the current
  stand-in has (setup used to be visible to the agent; now it genuinely isn't).
- `_pentest_step` unchanged in shape, but its hardcoded `http://web:8080` target needs to
  become whatever `<env_id>-website-frontend` resolves to (confirmed per-task in 4.1 step 4).
- **`_verify_step` can now be the real thing.** With artifact creation unblocked, write an
  `env_outcome_verifier` step with a real `file_artifact_id` pointing at a Python script that
  reproduces each task's existing `tests/test.sh` logic (technique-gated marker match, same
  anti-cheat ordering: check `technique` before comparing `ground_truth` to the submission).
  Needs `env_id` — now we have one, unlike the dind design where there was no declared env to
  point at.
- Keep `_capability_step` (verify_sandbox), `_snapshot_step` (snapshot_agent_state),
  `_collect_step`, `_aggregate_leg_step`, `_aggregate_fleet_step` — all real, unaffected by
  this rework.

### 4.3 Per-task rollout order

1. `dolibarr-idor` first (already our reference task locally; smallest known diff).
2. One more task from a *different* app (e.g. a `glpi-*` task) to confirm the backend-merge
   pattern generalizes rather than being dolibarr-specific (its entrypoint/seeding mechanics
   may differ app to app).
3. Only then fold the pattern into `ops/generate_from_sheet.py` as the default for every row,
   rather than hand-building each task's merge.

### 4.4 Not yet started / explicitly out of scope for this doc

- Any task whose environment has **more than 3 services** (none currently in this repo, but
  worth flagging: merging N-1 services into one "backend" image stops being a small diff past
  a certain complexity, and may need a different approach — revisit if/when such a task
  exists).
- The multi-stage, gate-checked, fleet-of-legs shape a mature pipeline like `synth-gen`'s
  actually has (see CHANGELOG.md's "why 114 steps" note) — this doc is only about getting one
  stage (deploy → pentest → verify) working for real per task; QC/gate steps on top of that
  are a later phase.

## 5. The option we're not pursuing right now, for the record

`deploy_sandbox` + `run_docker_container` is the *architecturally correct* answer and
requires none of §4's per-task image-merging — our existing 3-service `docker-compose.yaml`
would map almost directly onto 3 `run_docker_container` steps on one shared VM. It's blocked
for agent-initiated runs only. If this project ever wants that fidelity back, the path is:
generate the step JSON (still doable — `ops/hub.py`'s `publish_task()` publishes it fine,
publishing isn't blocked, only *running* is), and have a human run it via the hub UI or CLI
themselves. Not pursued in this session per explicit decision to go with the `deploy_env`
image-merge approach (§4) instead, since it stays within what can be driven end-to-end by an
agent.
