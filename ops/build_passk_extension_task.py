#!/usr/bin/env python3
"""pass@k extension: a SEPARATE hub task from construction. Given a COMPLETED
construction run's collect-task-bundle artifact id + its SANDBOX_NAME (to
derive VCHAN_VOLUME), publishes `attempts` fully independent pentest attempts
of ONE model, each on its own isolated sandbox (install_agent host mode),
loading the same already-built/already-QC'd task bundle (no re-injection, no
re-QC). No attempt depends on any other, so all `attempts` run concurrently.

WHY THIS IS A SEPARATE TASK FROM CONSTRUCTION (not one combined DAG): a real
run confirmed that a single 112-step task (construction's ~22 steps + 10
isolated attempt-branches x 9 steps each) with 10-way concurrent sandbox
deployment TERMINATEs with no error surfaced on this hub -- never tested at
that scale before (every prior working run topped out at 2-way concurrency /
~37 steps total). Splitting construction and pass@k into separate task
publishes keeps each one's own DAG size and concurrent-sandbox count small
regardless of how many pass@k attempts are requested; `--attempts` can also
be split further across multiple invocations of this same script (e.g. 5+5)
if even 10-way concurrency in ONE pass@k task turns out to be too large.

Reuses build_full_pipeline_task.py's `_isolated_pentest_branch` (same
isolated-sandbox pattern, same today's-session fixes: install_agent host
mode, sandbox_name-mode collect_artifacts, presence-based verify,
max_turns=100 as the real per-attempt limit) in its cross-task
`task_bundle_artifact_id` mode, so there is zero logic duplication between
construction's own (now-unused) same-task pentest path and this one.

Usage:
    python3 ops/build_passk_extension_task.py <hub_task_id> --project-id <id> \
        --task-bundle-artifact-id <id from construction's collect-task-bundle step> \
        --construction-sandbox-name <construction run's SANDBOX_NAME, e.g. pipeline-vm-1792014013> \
        --model azure_ai/DeepSeek-V4-Flash --model-label deepseek --harness opencode-cli \
        [--attempts 10] [--max-turns 100] [--publish] [--run --litellm-api-key <key>]
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402
import build_full_pipeline_task as base  # noqa: E402


def build_steps(task_bundle_artifact_id: str, construction_sandbox_name: str,
                 model: str, model_label: str, harness: str, effort: str | None,
                 construction_model: str = "anthropic/claude-sonnet-5",
                 attempts: int = 10, max_turns: int = 100,
                 sandbox_suffix: str | None = None,
                 project_id: str = "", include_judge_rubric: bool = True) -> list[dict]:
    # _isolated_pentest_branch/_verify_step_real/_judge_rubric_step read these
    # as module globals on `base`, not parameters -- patch them before building
    # any steps. SANDBOX_NAME here is THIS task's own attempt-sandbox prefix
    # (fresh per invocation via sandbox_suffix); VCHAN_VOLUME must match
    # construction's own value exactly (the vchan volume name baked into the
    # task bundle's docker-compose.yaml at construction time). PROJECT_ID is
    # stamped onto each deploy_sandbox step so Modal attributes the spend.
    suffix = sandbox_suffix or str(int(time.time()))
    base.SANDBOX_NAME = f"passk-{suffix}"
    base.VCHAN_VOLUME = f"{construction_sandbox_name}-vchan"
    base.PROJECT_ID = project_id

    steps = []
    for i in range(1, attempts + 1):
        label = f"{model_label}-{i}"
        steps += base._isolated_pentest_branch(
            label, model, effort, harness,
            depends_on_id="",  # unused in cross-task mode
            construction_model=construction_model,
            max_turns=max_turns,
            task_bundle_artifact_id=task_bundle_artifact_id,
            include_judge_rubric=include_judge_rubric,
        )
        sandbox_name = f"{base.SANDBOX_NAME}-{label}"
        steps.append(base._verify_step_real(label, sandbox_name=sandbox_name))
        steps.append(base._final_bundle_step(label, sandbox_name, f"verify-{label}"))
    return steps


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hub_task_id")
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--task-bundle-artifact-id", required=True)
    ap.add_argument("--construction-sandbox-name", required=True,
                     help="the construction run's SANDBOX_NAME, e.g. pipeline-vm-1792014013 "
                          "(used to derive the exact VCHAN_VOLUME baked into the task bundle)")
    ap.add_argument("--model", required=True)
    ap.add_argument("--model-label", default="deepseek")
    ap.add_argument("--model-effort", default=None)
    ap.add_argument("--harness", default="opencode-cli")
    ap.add_argument("--construction-model", default="anthropic/claude-sonnet-5",
                     help="model used for boot-target/judge-rubric helper steps")
    ap.add_argument("--attempts", type=int, default=10)
    ap.add_argument("--max-turns", type=int, default=100)
    ap.add_argument("--sandbox-suffix", default=None)
    ap.add_argument("--behavior-only", action="store_true",
                     help="drop the judge-rubric (R gate) step; score behavior/flag (0/1) only "
                          "-- the KangKang behavior-only MVP. Also skips the per-attempt Sonnet "
                          "judge call + test.sh run (cheaper/faster).")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--litellm-api-key", default=None)
    args = ap.parse_args()

    steps = build_steps(
        args.task_bundle_artifact_id, args.construction_sandbox_name,
        args.model, args.model_label, args.harness, args.model_effort,
        construction_model=args.construction_model,
        attempts=args.attempts, max_turns=args.max_turns,
        sandbox_suffix=args.sandbox_suffix,
        project_id=args.project_id, include_judge_rubric=not args.behavior_only,
    )
    print(f"built {len(steps)} steps for {args.hub_task_id!r} "
          f"({args.attempts} attempts, max_turns={args.max_turns})")
    for s in steps:
        print(f"  {s['id']:<28} {s['type']}")

    if not args.publish:
        print("\n--publish not given: nothing sent.")
        return

    status, out = hub.publish_task(args.hub_task_id, args.project_id, steps)
    print(f"\npublish -> HTTP {status}")
    if status not in (200, 201):
        raise SystemExit(out)

    if args.run:
        if not args.litellm_api_key:
            raise SystemExit("--run needs --litellm-api-key")
        status, out = hub.run_task(args.hub_task_id, args.project_id, litellm_api_key=args.litellm_api_key)
        print(f"\nrun_task -> HTTP {status}")
        print(out)


if __name__ == "__main__":
    main()
