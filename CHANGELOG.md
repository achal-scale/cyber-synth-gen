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
