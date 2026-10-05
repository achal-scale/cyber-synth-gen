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
