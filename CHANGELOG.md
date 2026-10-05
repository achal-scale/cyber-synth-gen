# Changelog

## v1 scaffold (this commit)

- Repo created: `achal-scale/cyber-synth-gen`, private, following `synth-gen`'s pipeline shape
  (sourcing -> construction loop -> gate -> fleet -> delivery), adapted to CVE/app selection and
  Harbor-format web-app pentest tasks instead of arXiv papers and RSI environments.
- Decisions locked for v1 (confirmed with Achal before building): new standalone repo; depend on
  `scaleapi/agentenv-framework` as the eventual execution engine (not yet wired up); web-app-only
  scope (browser/kernel/DNS/IoT deferred); fleet stage is pass@5 on a single model (DeepSeek
  V4-Flash) only, mid-tier/frontier stages deferred; sandbox-escape gate included in v1; builder
  creates the task, reviewer and attempter (fleet model) are separate roles not simulated by the
  builder.
- `gate/contract_gate.py`, `gate/oracle_noop_gate.py`: real, tested wrappers around
  `cyber-sample-tasks/tools/rubric_pipeline.py`'s existing Stage-1 checks and the
  `trajectories/{oracle,noop}/reward.txt` convention. Both live-tested against
  `batch_01/dolibarr-B1-sqli` (pass) and synthetic/missing-data fixtures (correct GATE-STOP).
- `gate/sandbox_escape_gate.py`: new, no synth-gen equivalent. Statically checks
  `docker-compose.yaml` for `cap_drop: [ALL]`, `security_opt: no-new-privileges`, no
  `privileged`/docker-socket/`cap_add`, and a memory limit; `read_only` rootfs and `pids_limit`
  are REVIEW not FAIL in v1 pending a per-task tmpfs audit. Live-tested against
  `batch_01/dolibarr-B1-sqli` — correctly GATE-STOPs on its current (unhardened) compose file,
  confirming the hardening work flagged in the FNA1 gap-analysis doc is real and not yet done.
- `gate/fleet_gate.py`: v1 scope only (single model, pass@5, no resumption). Live-tested against
  missing-trajectory (GATE-STOP) and a synthetic 3/5 fixture (measured, pass_rate 0.6).
- `ops/launch_fleet.py`: a documented stub, not a tested script — no agent harness exists yet to
  actually drive a model against a task. Written so the fleet gate's expected trajectory layout
  (`trajectories/passk/<trial>/reward.txt`) has one concrete caller to build against.
- `environment-eval/README.md`: capability-ladder proposal (unconfirmed with the customer),
  two-axis clustering (vuln-class + platform/category), and the partial-credit scoring gap —
  all documentation, not yet enforced by any check.
- Not yet built: agent-env Task/Env graph wiring (sourcing/pipeline-review mechanics are
  documented contracts, not executable graphs yet), automated candidate sourcing, multi-model
  fleet stages, delivery/report generation.

## v1 fixes after review (same session)

Flagged in review: no actual (env, vuln_type) input entry point existed, and no zip-packaging
step existed — both real gaps, not nitpicks. Fixed:

- `pipeline-review/new_task.py`: scaffolds a new task from exactly `<env> <vuln_type>
  <output_dir>` plus optional `--cwe`/`--cve`/`--ticket`. Live-tested: correct file/directory
  layout, correct task.toml field substitution. Does not auto-inject the vulnerability itself —
  that remains real per-task engineering work, consistent with the "injecting the vulnerability
  is where the most work is" point raised earlier in this project; the script fixes the input
  contract and removes boilerplate, not the judgment work.
- `ops/package_deliverable.py`: re-runs all four gates itself (does not trust a prior separate
  run) and only zips `task_dir` into a deliverable if every one passes; refuses on any missing
  required file. Adds a `MANIFEST.json` at the zip root recording each gate's verdict, so a
  reviewer can confirm the zip they received is what the gates actually checked. Live-tested:
  missing-required-paths detection (positive and negative), and the zip/MANIFEST assembly logic
  in isolation (full end-to-end run against a real task is currently blocked on no task in
  `batch_01` yet clearing the sandbox-escape gate — expected, not a bug, since that hardening
  work is itself still outstanding).
- Also closed a gap in `gate/sandbox_escape_gate.py`'s own test coverage: its passing path had
  never actually been exercised (only the GATE-STOP path had). Tested now with a synthetic
  hardened compose fixture — confirmed correct.

## ops/launch_fleet.py implemented and live-tested

Implemented `run_one_trial` (was a `NotImplementedError` stub), following the architectural
lesson from reading synth-gen's `gate/run_attempt.py`: the script owns its own deadline
(`[agent].timeout_sec` + a 300s setup margin, not the caller's step timeout), launches
`--agent-cmd` as a subprocess under that deadline, and stages/runs the verifier itself
afterward regardless of what the agent command did.

Live-tested end to end against a real copy of `batch_01/dolibarr-B1-sqli` (real Docker boot,
real MariaDB/Dolibarr stack, real verifier run) with a dummy `--agent-cmd "true"`:
- **Found and fixed a real bug**: staging `/tests` and running the verifier as the task's
  default non-root `agent` user (uid 1001) fails with permission denied. Fixed by running those
  specific exec calls as `--user root`, consistent with this project's own stated convention
  (`cyber-sample-tasks/AGENTS.md`: `environment_mode = "shared"` means the verifier runs as
  root). The `finally`-block teardown correctly ran even while this bug was still present,
  confirmed by checking for leftover containers afterward (none).
- After the fix: full lifecycle confirmed — boot, stage as root, run `test.sh` as root, read
  `/logs/verifier/reward.txt` (correctly `0`, with the real verifier's own reason: "secret was
  not read through the intended sortfield SQL injection"), write
  `trajectories/passk/1/reward.txt`, teardown.
- Isolated (mocked-subprocess) test of the `killed-at-budget` path: confirmed the timeout is
  caught, the reward file is written with the sentinel, and teardown still fires via `finally`.
  First attempt at this test had a bug in the TEST ITSELF (truncated recorded calls to `cmd[:2]`,
  so "down" could never match) — re-verified correctly afterward.

Not yet tested live: a real model actually solving the task via a real `--agent-cmd` (needs the
org's actual agent-harness invocation, which this script takes as a caller-supplied argument and
does not assume — see the module docstring).

## Closed the TR4/TR5/EV6 gap, added standalone re-QC

Found via direct question: contract_gate.py correctly excludes rubric_pipeline.STAGE2 (TR4, TR5,
EV6) because they need pass@k data that doesn't exist at that point in the construction loop --
but nothing ever checked them AFTER pass@k data existed either. Three of the project's 24-27
rubrics were structurally unreachable in this pipeline. Fixed:

- `gate/stage2_gate.py`: runs rubric_pipeline.check() filtered TO STAGE2 ids, meant to run after
  fleet_gate.py confirms trajectories/passk/ is real. Live-tested against
  `batch_01/dolibarr-B1-sqli` -- correctly GATE-STOPs naming TR4/TR5 (the same pre-existing,
  repo-wide failing state confirmed earlier this project on an untouched reference task too, not
  something this gate caused).
- Wired into `ops/package_deliverable.py` as gate 5, skipped under `--skip-fleet` same as the
  fleet gate. Re-verified the `--skip-fleet` path still stops at the same earlier gate
  (sandbox_escape) as before, confirming stage2 is correctly never reached when skipped.
- `ops/qc_recheck.py`: new standalone re-verify entry point (synth-gen's `qc-pipeline/`
  equivalent) -- runs all five gates against an already-built task, independent of scaffolding
  or packaging, and unlike every other gate script here does NOT stop at the first failure: it
  runs every gate and reports the full current state in one pass. Live-tested against
  `batch_01/dolibarr-B1-sqli`: correctly shows contract+oracle_noop passing while
  sandbox_escape/fleet/stage2 all report their real current failing state in one consolidated
  report.

## Real agent-env adoption: ComposeEnv, live-tested against a real task

Previously flagged (and the user chose to proceed anyway, understanding the cost): none of
agent-env's built-in `Env` types fit our 4-service, non-protocol-speaking task shape.

Investigated the installed package source directly (`uv tool install agentenv-framework`,
v0.9.1267) rather than guessing, and found the real integration point: `LocalSandbox`
(`providers/sandbox_providers/local_sandbox.py`) is a generic VM-mode sandbox whose work
directory can hold an arbitrary `docker-compose.yml`, with its own `terminate()` already
tearing one down if present.

Wrote `agentenv_plugin/compose_env.py`'s `ComposeEnv(Env)`: copies a task's `environment/`
directory onto a `LocalSandbox`'s work dir, boots it via the sandbox's own `exec_script`, resolves
the published gateway port, and returns a `DeployedSandboxEnv` carrying the gateway URL in
metadata (no agentenv_protocol "card" -- these are black-box HTTP tasks, not MCP tool-callers).

Live-tested against a real copy of `batch_01/dolibarr-B1-sqli/environment` (not a fixture):
deploy -> real Docker boot -> `GET /health` returned `200 {"status":"ok"}` -> `terminate()` ->
independently confirmed via `docker ps`/`docker network ls` (not just a clean return value) that
every container and network was actually gone.

Not yet done: registering `ComposeEnv` through agent-env's actual config/registry and running it
via a real `agent-env run <bundle>` Task (this was exercised as a standalone Python script, not
through the framework's own CLI/DAG yet); converting `gate/*.py` into real `TaskStep`s;
converting `ops/launch_fleet.py`'s trial loop into a `run_code`-style step.

## ComposeEnv proven through a real agent-env Task, not just standalone Python

Registered `ComposeEnv` via `.agentenv/config.toml`'s `[envs] impls`, confirmed loading via
`agent-env plugin check` (ok). Attempted the natural bundle-authoring path
(`envs/dolibarr-b1-sqli/env.toml`) and hit a real framework limitation: bundles cannot author an
env in this release at all (`writing an env isn't supported yet` -- the bundle writer table only
implements artifacts/agents/evals). Worked around it correctly: registered the env directly via
`ComposeEnv.put(...)`, then ran a real bundle (`bundle/tasks/compose_smoke.json`: `deploy_env` ->
`run_code`) referencing it.

Hit and fixed two more real issues along the way, each confirmed via the actual error before
fixing (not guessed):
- `run_code` shells out to the `timeout` coreutil, absent on macOS by default -- fixed via
  `brew install coreutils` + the gnubin PATH prefix.
- `run_code`'s `args` are static/author-time literals and `results` only holds prior `run_code`
  outputs -- `context.deployed_envs`' metadata (our `gateway_url`) is never passed in, and there
  is no templating mechanism. Worked around by having the script relocate the sandbox's work dir
  itself (`~/.agent-env-sandboxes` glob for the one holding a `docker-compose.yml`); the real fix
  (a framework change, or an instance-store query by env_id) is noted as follow-up in
  `bundle/README.md`, not implemented.

Final result, independently verified (not just a clean exit code): read the task instance's
stored `script_results` directly -- `{"status": 200, "body": "{\"status\":\"ok\"}"}` -- then
confirmed via `docker ps`/`docker network ls` that automatic teardown left nothing running.

## Gate scripts wired in as real TaskSteps

`contract_gate.py`, `oracle_noop_gate.py`, `sandbox_escape_gate.py` already matched `run_code`'s
`run(input) -> JSON` contract with zero changes needed -- packaged as FileArtifacts and run as
`run_code` steps in a new `bundle/tasks/gates_smoke.json`, against the same `dolibarr-b1-sqli`
env deployment. `task_dir`/`rubric_pipeline_path` are static author-time paths, so (unlike
`gateway_url`) no workaround was needed to pass them in.

Live-tested end to end: `contract` and `oracle_noop` passed; `sandbox_escape` failed with the
identical GATE-STOP message every standalone run this session has produced (confirming the
TaskStep wiring is faithful, not a different code path), the task correctly failed overall, and
teardown still ran automatically on failure (confirmed clean via `docker ps`).

Hit one unrelated flake: `LocalSandbox`'s auto-generated work-dir name (via `tempfile.mkdtemp`,
whose suffix charset includes `_`) occasionally produces a name Docker's image-reference parser
rejects when Compose derives the project name from it. Framework-level, not fixable from this
plugin without diverging from `LocalSandbox.terminate()`'s own naming convention (which would
break teardown); resolved by retrying with a fresh random sandbox_id.

`fleet_gate.py`/`stage2_gate.py` still not wired in -- both need real `trajectories/passk/` data,
which still doesn't exist (blocked on `ops/launch_fleet.py --agent-cmd`, per its own docstring).

## Dropped sandbox_escape_gate from the default pipeline

Per direction: sandbox-escape hardening was specifically an FNA1 (customer feedback) requirement,
not something core to this pipeline's own process. Removed it from `ops/package_deliverable.py`'s
and `ops/qc_recheck.py`'s default gate sequences -- both now run contract -> oracle_noop (->
fleet -> stage2 when not --skip-fleet). The gate script itself and its TaskStep wiring in
`bundle/tasks/gates_smoke.json` are untouched, for whoever still needs it later.

Re-verified: `batch_01/dolibarr-B1-sqli` now passes `qc_recheck.py --skip-fleet` cleanly (it was
previously blocked here purely on unhardened containers, which was never a defect in the task
itself).
