# pass@k + hardening progress — `can/passk-dev`

**From:** Can
**Branch:** `can/passk-dev` (off `master`), commits `ed48f9d`, `82a9a7a`
**Goal of this work:** get KangKang's behavior-only MVP running on a *single-task* bundle,
plus a hardening loop driven by the repo's own hardening skill — reusing your pass@k steps
rather than forking them. This doc is meant to be picked apart and folded back into the main
pipeline; it calls out the hacks and the things we found but have **not** fixed.

---

## TL;DR of what changed

1. **pass@k was never actually running in parallel.** The biggest find. Fixed — see §1.
2. **Behavior-only (0/1 flag) mode** added, per KangKang's MVP (drop the rubric). §2
3. **Cost attribution** (`project_id`) stamped on every `deploy_sandbox`. §2
4. **Hardening loop** (`drive_hardening_loop.py`) — harden → pass@k → decide, looped. §3
5. **Registered `batch_01/dolibarr-B1-sqli` as a hub bundle** so pass@k can load it. §4
6. **Open issues we did NOT fix:** solution leak, verifier not technique-scoped, a hacky
   step drop, laptop-driven loop fragility. §5 — **please read this one.**
7. Modal infra experiments (lower priority). §6

---

## 1. The parallelization bug (most important)

A pass@k run of N attempts was taking hours because **the attempt branches were running
serially, not concurrently** — and not because of Modal.

Root cause is the scheduler's `depends_on` semantics (`agent_env/task/task.py`
`_build_scheduler_state`):

- `depends_on=None` (omitted) = **"depends on all prior steps"** → every branch serialized
  behind the previous one (~20 min apart).
- `depends_on: []` (explicit empty) = **no deps** → branches run concurrently.

The isolated pentest branches were omitting `depends_on` on their first step, so the
scheduler chained all N branches into one line. We now set `deploy_sandbox.depends_on = []`
in cross-task (pass@k) mode (and gate only on construction's last step in combined mode).

**This alone turned an N-hour run into a ~single-attempt-wall-clock run.** If your pipeline
assembles branches the same way, this is worth checking first. See
`ops/build_full_pipeline_task.py` `_isolated_pentest_branch` (the comment block spells it out).

---

## 2. pass@k pipeline changes (`ops/build_passk_extension_task.py`)

pass@k is published as a **separate hub task from construction** (not one combined DAG). A
single 112-step task with 10-way concurrent sandbox deploy `TERMINATE`d with nothing surfaced
on the hub; splitting construction and pass@k keeps each DAG small regardless of attempt count.
Each attempt is one isolated sandbox loading the already-built `collect-task-bundle` artifact
(no re-injection / re-QC).

New flags:

- `--behavior-only` — drops the `judge-rubric` step; scores a bare **0/1 did-it-get-the-flag**
  per attempt (the KangKang MVP). Also skips the per-attempt Sonnet judge call + `test.sh`,
  so it's cheaper/faster.
- `--project-id` — stamped as `metadata.attribution.project_id` on every `deploy_sandbox`
  so Modal attributes sandbox spend to a real project (monorepo rule: no un-attributed
  sandboxes). Threaded through harden + loop too.
- `--pentest-timeout` — per-attempt wall-clock backstop. Default is effectively none
  (`max_turns` governs); set ~1800 (30 min) **only for fast testing** so a straggler branch
  becomes a tolerant MISSING instead of hanging the run. Opt-in on purpose — we did NOT want
  production runs silently capping long legitimate pentests.
- `--vchan-volume` — see §4 (needed for single-task bundles).

The per-attempt verify step is non-fatal (`fail_task_on_error=False`) and the whole branch is
non-fatal, so one branch failing can't take down a sibling branch that already succeeded (a
real run showed exactly this cross-branch kill).

---

## 3. The hardening loop (`ops/build_harden_task.py` + `ops/drive_hardening_loop.py`)

The hub DAG is static, so "if still too easy, harden again" can't live inside a task. The loop
is an **external driver**. Each round:

1. **HARDEN** — a Sonnet `claude-code-cli` agent on one VM (host mode, real docker) applies the
   repo's hardening playbook (`cyber-sample-tasks/skills/harden_strategies/harden_strategies.md`,
   embedded into the prompt). Two axes, in order: **VALIDITY first (P0)** — close every
   unintended path to the secret — then **DIFFICULTY** — strip format/location/comment hints
   from `instruction_L0.md` while keeping the flaw and the L1/L2 hint ladder.
2. **verify-oracle** — deterministic gate: run `solution/solve.sh` and confirm the intended
   exploit *still* discloses the flag (reuses the `audit-technique-check` verifier). If the
   hardening broke solvability, the round is invalid and the loop **stops** rather than shipping
   an unsolvable bundle.
3. **PASS@K** on the hardened bundle (identical steps to standalone pass@k).
4. **DECIDE** — accept when pass rate ≤ `--tolerance` (oracle already OK); else feed the
   hardened bundle into the next round, up to `--max-rounds`.

Target (KangKang MVP wording): pass@k by the weak solver **as low as possible while
`solution.sh` still passes**.

Prompt gotcha we hit: `prompt_agent._apply_seed` treats `<key>` angle-bracket tokens as
run-time **seed placeholders**, so embedding a skill that literally contains `<value>` made the
hub run form demand a seed ("Row 1 is missing a value for `<value>`"). We sanitize `<x>`→`[x]`
in the embedded skill text (meaning preserved). Worth knowing if you embed any skill/markdown
into a `prompt_agent` step.

---

## 4. Registering `batch_01/dolibarr-B1-sqli` as a hub bundle (`ops/register_task_bundle.py`)

We moved off the dolibarr **estate** (`full-pipeline-round-1-1792077214[-passk]`) because it's a
**multi-task estate** (FLAG1–6, several techniques, ~100% pass) — not the one-vuln-one-flag unit
the initiative wants. KangKang pointed us at the single-task `batch_01/dolibarr-B1-sqli` (one
flag `FLAG_B1`, technique `sortfield_injection`).

That task is **repo files, not a registered hub artifact**, and there's no ready-made
"task-dir → hub bundle" tool. So:

- `register_task_bundle.py` registers a task directory as a **`FileArtifactUniverse`** via
  `put_bundled` (the same universe type `collect-task-bundle` emits). It derives the S3 prefix
  the same way agent-env's own `artifact file-artifact-universe put-bundled` CLI does
  (`s3://<configured-bucket>/file_artifact_universe/<id>/`), and **excludes** `trajectories/`,
  `.git`, caches — so the bundle is just the task definition (34 files, 0.29 MB vs 5.4 MB raw).
- Registered id: **`can-dolibarr-b1-sqli-task`** (prod artifact catalog).
- Setup needed: `agentenvhub-sdk` installed **from scale-pypi** (NOT an editable source install —
  that resolves private deps like `scale-sandbox` from public PyPI and fails) into a venv, plus
  an AWS SSO session (`AWS_PROFILE=production-developer`). The `install-agentenvhub-sdk` skill
  has the exact CodeArtifact-token install.

**vchan volume difference (the `--vchan-volume` flag).** The verifier reads a per-boot
`/verifier_token` off a shared Docker "vchan" volume and curls the target's
`/internal/diag/audit` with it. The two bundle styles name that volume differently:

| bundle | vchan declaration | runtime name | flag |
|---|---|---|---|
| estate (`full-pipeline-round-1-…`) | external `<sandbox>-vchan` | `full-pipeline-round-1-…-vchan` | default (`<construction-sandbox-name>-vchan`) |
| `batch_01/dolibarr-B1-sqli` | internal `vchan: null`, booted `-p construction` | `construction_vchan` | `--vchan-volume construction_vchan` |

So single-task batch_01 runs need `--vchan-volume construction_vchan`; without it the verify
step mounts a nonexistent volume and every attempt fails verification even on a real solve. We
threaded this through pass@k **and** both legs of the harden loop (`82a9a7a`).

Run command (pass@3 smoke currently in flight as `can-b1-passk-1`):

```bash
~/.venvs/vmprobe/bin/python ops/build_passk_extension_task.py can-b1-passk-1 \
  --project-id <PROJECT_ID> --task-bundle-artifact-id can-dolibarr-b1-sqli-task \
  --construction-sandbox-name dummy --vchan-volume construction_vchan \
  --model azure_ai/DeepSeek-V4-Flash --behavior-only --attempts 3 --pentest-timeout 1800 \
  --publish --run --litellm-api-key "$LITELLM_API_KEY"
```

---

## 5. Open issues we did NOT fix (please read)

### 5a. Solution leak — LATENT, mitigation drafted but NOT wired
The loadable bundle contains **`solution/solve.sh`** (the full ~110-line intended exploit) and
`tests/` (behavior check + rubric). `load_artifact` drops the whole bundle onto the same sandbox
the solver runs on (`/app/task`). The verifier prevents **faking** a flag (it needs the vchan
token), but it does **not** prevent a solver from **reading the intended exploit off disk** and
replaying it — which would inflate the pass rate and contaminate the difficulty signal.

- Observed runs so far showed **independent discovery**, not copying, so this is a latent risk
  rather than a confirmed contamination — but it's unguarded.
- We drafted `ops/verify_scripts/scrub_bundle.py` (deterministic host-side scrub that deletes
  `solution/` before the solver runs) but it is **NOT wired into the pipeline** and not
  registered. It was blocked on the same `agentenvhub_sdk` registration wall; that wall is now
  cleared (§4), so wiring it is unblocked work, just not done.
- **Recommendation:** decide whether the loadable bundle should be scrubbed of `solution/`
  (+ grader config) at load time, as a standard pipeline step, not a bolt-on.

### 5b. Verifier is not technique-scoped
`audit-technique-check` credits **any** flag that comes back `retrieved=true` with *a* technique.
For a single-task bundle (one flag) that's fine. But there's no `--expected-technique` gate, so
on a multi-flag/estate bundle it would credit the wrong mechanism. If single-task is the
delivery unit this is moot; if estates stay, the verifier needs technique scoping.

### 5c. `collect-{label}` step dropped — HACKY, temporary
We **removed** the per-attempt `collect-{label}` `collect_artifacts` step from each pass@k
branch (`build_full_pipeline_task.py` `_isolated_pentest_branch`). Reason: (1) it had **no
downstream consumer** — nothing read its `submission.txt`/`report.md` output, and the flag is
graded via the vchan/audit endpoint, not these files; (2) it was **hard-failing** after a
`base_path` change and, being in a branch, could take the run down. Dropping it removed the
error and lost nothing *currently used*.
- This is a **temporary hack**, not a real fix. If you want those raw solver artifacts back for
  human inspection, the thing to revisit is why `collect_artifacts` on the `agent_logs` volume
  errored (likely the `/app/task`-as-one-file vs recursive-enumerate quirk at
  `build_full_pipeline_task.py:360`), then re-wire it to an actual consumer. It is **not** behind
  a flag — re-adding means restoring the step.

### 5d. `show_passk_result.py` reads all-MISSING mid-run
The hub run-status aggregate (`script_results`) only populates once the run is **terminal**, so
mid-run every branch reads MISSING / 0% — which looks like a total failure but isn't. Minor, but
confusing; a real fix would read per-step results live instead of the aggregate.

### 5e. Loop is laptop-driven + open questions
- `drive_hardening_loop.py` polls from your shell — it dies if the laptop sleeps or SSO/VPN
  expires. It is **not** a fire-and-forget server job. Long multi-round runs need a persistent
  host.
- `--tolerance 0.30` is a **guess** — "as low as possible while solve.sh passes" has no agreed
  number. Needs KangKang.
- Open product question: is the delivery unit a **single-task bundle** or an **estate**? Drives
  5b and the whole "why 3 flags" confusion.

---

## 6. Modal infra experiments (lower priority)

We chased a suspected "Modal can't handle 10 concurrent sandboxes" problem. It was a
**misdiagnosis** — the branches were serialized (§1), never actually concurrent. Findings:

- `ops/vm_concurrency_probe.py` — a local harness that calls Modal `create_vm` N-way directly.
  It proved **Modal handles 10-way concurrent fine** in a funded environment.
- The main Modal environment was **out of budget** (`ResourceExhaustedError: exceeded spend
  limit`); `genai-agent-env` is funded. Note this only matters for the **local probe** — the
  Modal client reads `MODAL_ENVIRONMENT` from the shell. **Hub runs do NOT read it**; their
  sandbox environment is chosen server-side by modal-proxy. (We initially put
  `MODAL_ENVIRONMENT=genai-agent-env` in front of hub-run commands — that's a **no-op** for hub
  runs. If you want hub runs pinned to a Modal env, that's a modal-proxy-side setting.)
- The pentest path uses the **experimental `vm_runtime`** (`sandbox_mode: "vm"`, a nested-KVM
  VM) rather than container-in-gVisor. That appears intentional (real docker inside), not an
  accident — flagging in case it matters for your cost/latency.

---

## Files touched / added (all under `ops/`)

| file | what |
|---|---|
| `build_full_pipeline_task.py` | parallelization fix; attribution; non-fatal verify; dropped `collect-{label}`; threaded judge/timeout params |
| `build_passk_extension_task.py` | `--behavior-only`, `--project-id`, `--pentest-timeout`, `--vchan-volume` |
| `build_harden_task.py` | **new** — the per-round harden task (harden → oracle gate → collect) |
| `drive_hardening_loop.py` | **new** — the harden→pass@k→decide loop driver |
| `register_task_bundle.py` | **new** — register a repo task dir as a hub `FileArtifactUniverse` |
| `verify_scripts/scrub_bundle.py` | **new, DEFERRED/unwired** — solution-scrub draft (5a) |
| `vm_concurrency_probe.py`, `vm_hub_probe.py` | **new** — the Modal concurrency experiments (§6) |
| `show_passk_result.py` | **new** — read a finished pass@k run's per-branch PASS/FAIL |

---

## What I think is directly reusable for you

- **The parallelization fix (§1)** — if your branches omit `depends_on`, this is a free speedup.
- **`--behavior-only`** — matches the MVP; cheaper/faster signal.
- **`register_task_bundle.py` + the `--vchan-volume` pattern** — lets any single-task repo bundle
  run on pass@k without the estate's external-volume assumption.
- **The harden loop** — a working validity-then-difficulty loop using the repo skill.

The two things I'd prioritize folding in properly (vs our hacks): **5a (solution scrub as a real
load-time step)** and **5c (restore/retire `collect-{label}` deliberately)**.
