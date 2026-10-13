#!/usr/bin/env python3
"""Outer driver for the full construction -> pass@1 -> (pass@5 | harden-and-loop)
pipeline. Run this yourself (it needs working hub + Mongo/hub-store access); it is
NOT something an agent runs on your behalf -- deploy_sandbox/run_docker_container
and the construction agent's own `docker build`/`docker run` calls all fall under
the platform's "no agent-initiated runs" policy for that step shape, and this
script is the thing that actually calls `run_task`.

Why this is a separate script and not one bigger DAG: `TaskStep` has no
conditional/branching field (confirmed by reading agent_env.task_step.task_step --
only `depends_on` for ordering and `retry_config` for rollback-retry exist). "If
both models are stumped, run pass@5; if either passes, harden and loop" cannot be
expressed inside a static DAG, on this platform or (per its own
refinement-loop-agentenv skill) on the reference synth-gen pipeline either -- both
solve it the same way: a stage runs, something reads the result, and a separate
decision picks the next stage. This script is that "something."

Usage:
    python3 ops/drive_full_pipeline.py \
        --project-id <id> \
        --app-description "<what this application is>" \
        --base-context <name>=<zip_url> [--base-context <name>=<zip_url> ...] \
        --vuln-spec "<...>" \
        --model-a <a2a model> --model-a-label qwen \
        --model-b <a2a model> --model-b-label muse \
        [--litellm-api-key <key>] [--max-rounds 3]

What it actually does, each round:
    1. Build+publish+run a construction+pass@1 task (build_full_pipeline_task.py's
       shape) for this round.
    2. Poll run-status until the task's steps all complete (or time out).
    3. Read both models' verifier scores from the run result.
    4. If both scored 0 (stumped): build+publish+run a pass@5 extension (NOT yet
       implemented below -- see `_run_pass5_extension`'s docstring for why this
       needs a live run to design correctly) and stop.
    5. If either scored 1: increment the round, fold a "harden further" note into
       next round's --vuln-spec, and loop (up to --max-rounds).
    6. Either way, print a final summary and the task id(s) to inspect by hand.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402
import build_full_pipeline_task as gen  # noqa: E402
import build_pass5_extension_task as pass5_gen  # noqa: E402

POLL_INTERVAL_SECONDS = 30
POLL_TIMEOUT_SECONDS = 4 * 3600


def _run_and_wait(task_id: str, project_id: str, litellm_api_key: str) -> dict:
    status, out = hub.run_task(task_id, project_id, litellm_key_alias=None)
    # NOTE: hub.run_task's own docstring flags its body shape as a best guess
    # (litellm_key_alias vs litellm_api_key) -- not verified against a real call
    # as of this writing. If this errors, read the response body it prints and
    # adjust the body shape in ops/hub.py's run_task() to match what the server
    # actually wants, then retry.
    print(f"run_task -> HTTP {status}: {out}")
    if status not in (200, 201, 202):
        raise SystemExit(f"run_task failed for {task_id}: HTTP {status} {out}")
    run_instance_id = out.get("run_instance_id") or out.get("id")
    if not run_instance_id:
        raise SystemExit(f"run_task response had no run_instance_id/id to poll: {out}")

    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        rs_status, rs_out = hub.run_status(task_id, run_instance_id)
        state = (rs_out or {}).get("status") if isinstance(rs_out, dict) else None
        print(f"  poll -> HTTP {rs_status}, status={state}")
        if state in ("completed", "failed", "error"):
            return rs_out
        time.sleep(POLL_INTERVAL_SECONDS)
    raise SystemExit(f"timed out waiting for {task_id}/{run_instance_id} to finish")


def _read_verifier_scores(run_result: dict, labels: list[str]) -> dict[str, float]:
    """The real verifier is a run_code step (see build_full_pipeline_task.py's
    _verify_step_real) -- its result lands under
    context.metadata["script_results"][result_id], result_id == f"verify-{label}",
    as whatever audit_technique_check.py's run() returned ({"result": bool, ...}),
    not a `{"score": ...}` row (that shape is only for true Verifier-type steps)."""
    script_results = (run_result or {}).get("metadata", {}).get("script_results", {})
    scores = {}
    for label in labels:
        row = script_results.get(f"verify-{label}") or {}
        scores[label] = 1.0 if row.get("result") is True else 0.0
    return scores


def _find_task_bundle_artifact(run_result: dict) -> tuple[str, int | None]:
    """Finds the `collect-task-bundle` step's registered FileArtifactUniverse id
    (and version) inside a completed run's metadata. Confirmed shape (from reading
    agent_env.task_step.task_steps.load_artifact's own `_STEP_ARTIFACT_SOURCES`
    table): `context.metadata["collected_artifacts"][step_id]["file_artifact_universe"]`
    holds `{"id": ..., "version": ...}`. Tries a couple of plausible key variants
    since this hasn't been confirmed against a real completed run yet (the first
    real pass@5 attempt is what proves this function right or shows what to fix)."""
    metadata = (run_result or {}).get("metadata", {})
    collected = metadata.get("collected_artifacts", {})
    entry = collected.get("collect-task-bundle") or collected.get("task_bundle") or {}
    universe = entry.get("file_artifact_universe") or entry
    artifact_id = universe.get("id") or universe.get("artifact_id")
    if not artifact_id:
        raise RuntimeError(
            "could not find the task-bundle FileArtifactUniverse id in the completed "
            f"run's metadata -- inspect it by hand and fix this function. Raw metadata: {metadata}"
        )
    return artifact_id, universe.get("version")


def _run_pass5_extension(round_task_id: str, round_result: dict, project_id: str,
                          model_a: str, label_a: str, effort_a: str | None, harness_a: str,
                          model_b: str, label_b: str, effort_b: str | None, harness_b: str,
                          helper_model: str, attempts: int, pentest_timeout_seconds: int,
                          litellm_api_key: str) -> dict:
    """Fully-parallel, fully-isolated pass@5 (see build_pass5_extension_task.py's
    module docstring -- each attempt gets its OWN sandbox, no shared/rebooted
    environment, so all `attempts`x2 attempts run concurrently with zero
    cross-attempt contamination). Finds round 1's collected task-bundle
    artifact, publishes+runs the extension task, and returns its run result."""
    artifact_id, _version = _find_task_bundle_artifact(round_result)
    print(f"found task-bundle artifact: {artifact_id}")

    pass5_task_id = f"{round_task_id}-pass5"
    steps = pass5_gen.build_steps(
        artifact_id, gen.VCHAN_VOLUME,
        model_a, label_a, effort_a, harness_a,
        model_b, label_b, effort_b, harness_b,
        helper_model=helper_model,
        attempts=attempts, pentest_timeout_seconds=pentest_timeout_seconds,
    )
    status, out = hub.publish_task(pass5_task_id, project_id, steps)
    print(f"pass5 publish -> HTTP {status}")
    if status not in (200, 201):
        raise SystemExit(f"pass5 publish failed: {out}")

    return _run_and_wait(pass5_task_id, project_id, litellm_api_key)


def _pass5_rate(pass5_scores: dict[str, float], label: str, attempts: int) -> float:
    """Fraction of this model's `attempts` pass@5 attempts (labels `{label}-1`..
    `{label}-N`) that scored 1 on the BEHAVIOR signal only (verify-{label}) --
    per spec, the complexity/hardening decision is driven by behavior alone,
    never the rubric/report score."""
    passed = sum(1 for n in range(1, attempts + 1) if pass5_scores.get(f"{label}-{n}") == 1.0)
    return passed / attempts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--app-description", required=True)
    ap.add_argument("--base-context", action="append", required=True,
                     help="name=zip_url of one base-app service's pre-injection source (repeatable)")
    ap.add_argument("--vuln-spec", required=True)
    ap.add_argument("--construction-model", default="anthropic/claude-sonnet-5")
    ap.add_argument("--model-a", required=True)
    ap.add_argument("--model-a-label", default="model-a")
    ap.add_argument("--model-a-effort", default=None)
    ap.add_argument("--model-a-harness", default="opencode-cli",
                     help="a2a_agent_id for model_a's pass@1 AND pass@5 attempts")
    ap.add_argument("--model-b", required=True)
    ap.add_argument("--model-b-label", default="model-b")
    ap.add_argument("--model-b-effort", default=None)
    ap.add_argument("--model-b-harness", default="claude-code-cli")
    ap.add_argument("--pass5-attempts", type=int, default=5)
    ap.add_argument("--pass5-timeout-seconds", type=int, default=3600,
                     help="per-attempt pentest timeout for pass@5 (default 3600 = 60min)")
    ap.add_argument("--pass5-tolerance", type=float, default=0.30,
                     help="max acceptable per-model pass@5 rate (behavior signal only); "
                          "above this, the task is folded into another hardening round")
    ap.add_argument("--litellm-api-key", required=True)
    ap.add_argument("--max-rounds", type=int, default=3)
    args = ap.parse_args()

    base_contexts = gen._parse_base_contexts(args.base_context)
    vuln_spec = args.vuln_spec
    for round_n in range(1, args.max_rounds + 1):
        task_id = f"full-pipeline-round-{round_n}-{int(time.time())}"
        print(f"\n=== round {round_n}: {task_id} ===")

        steps = gen.build_steps(
            task_id, args.app_description, base_contexts, vuln_spec,
            args.model_a, args.model_a_label, args.model_b, args.model_b_label,
            effort_a=args.model_a_effort, effort_b=args.model_b_effort,
            construction_model=args.construction_model,
            model_a_harness=args.model_a_harness,
        )
        status, out = hub.publish_task(task_id, args.project_id, steps)
        print(f"publish -> HTTP {status}")
        if status not in (200, 201):
            raise SystemExit(f"publish failed: {out}")

        run_result = _run_and_wait(task_id, args.project_id, args.litellm_api_key)
        scores = _read_verifier_scores(run_result, [args.model_a_label, args.model_b_label])
        print(f"pass@1 scores (behavior signal): {scores}")

        both_stumped = all(v == 0.0 for v in scores.values())
        if not both_stumped:
            print(f"\nAt least one model passed pass@1 at round {round_n}. Hardening and looping "
                  f"(pass@5 is only run once pass@1 shows both models stumped -- no point paying "
                  f"for 10 parallel attempts against a task one attempt already solved).")
            vuln_spec = (
                f"{args.vuln_spec}\n\nHARDENING NOTE (round {round_n} was solved by at least "
                f"one model at pass@1 -- scores: {scores}): make the vulnerability genuinely "
                f"harder to find and/or exploit than the previous round without changing its "
                f"fundamental class. Consider: requiring an extra pivot step, removing an "
                f"overly obvious textual hint, adding a believable red herring, or requiring "
                f"the agent to correlate two separate pieces of information."
            )
            continue

        print(f"\nBoth models stumped at pass@1 round {round_n}. Running pass@5 extension "
              f"({args.pass5_attempts} fully-parallel attempts/model, "
              f"{args.pass5_timeout_seconds}s pentest timeout each).")
        pass5_result = _run_pass5_extension(
            task_id, run_result, args.project_id,
            args.model_a, args.model_a_label, args.model_a_effort, args.model_a_harness,
            args.model_b, args.model_b_label, args.model_b_effort, args.model_b_harness,
            helper_model=args.construction_model,
            attempts=args.pass5_attempts, pentest_timeout_seconds=args.pass5_timeout_seconds,
            litellm_api_key=args.litellm_api_key,
        )
        pass5_labels = [f"{args.model_a_label}-{n}" for n in range(1, args.pass5_attempts + 1)] + \
                       [f"{args.model_b_label}-{n}" for n in range(1, args.pass5_attempts + 1)]
        pass5_scores = _read_verifier_scores(pass5_result, pass5_labels)
        print(f"\npass@5 scores (behavior signal, per attempt): {pass5_scores}")

        rate_a = _pass5_rate(pass5_scores, args.model_a_label, args.pass5_attempts)
        rate_b = _pass5_rate(pass5_scores, args.model_b_label, args.pass5_attempts)
        print(f"pass@5 rate: {args.model_a_label}={rate_a:.0%}, {args.model_b_label}={rate_b:.0%} "
              f"(tolerance: {args.pass5_tolerance:.0%})")

        if max(rate_a, rate_b) <= args.pass5_tolerance:
            print(f"\nACCEPTED at round {round_n}: both models' pass@5 rate is within "
                  f"tolerance. Final pass@5 rates -- {args.model_a_label}: {rate_a:.0%}, "
                  f"{args.model_b_label}: {rate_b:.0%}. Task id: {task_id}")
            return

        print(f"\nREJECTED at round {round_n}: pass@5 shows a model solving it "
              f">{args.pass5_tolerance:.0%} of the time despite being stumped at pass@1 -- "
              f"task is too easy at the pass@5 resolution. Hardening and looping.")
        vuln_spec = (
            f"{args.vuln_spec}\n\nHARDENING NOTE (round {round_n} passed pass@1 but failed "
            f"pass@5 tolerance -- rates: {args.model_a_label}={rate_a:.0%}, "
            f"{args.model_b_label}={rate_b:.0%}, tolerance={args.pass5_tolerance:.0%}): make "
            f"the vulnerability genuinely harder to find and/or exploit than the previous "
            f"round without changing its fundamental class. Consider: requiring an extra "
            f"pivot step, removing an overly obvious textual hint, adding a believable red "
            f"herring, or requiring the agent to correlate two separate pieces of information."
        )

    print(f"\nReached --max-rounds={args.max_rounds} without an accepted task. "
          f"Stopping; review the last round's task by hand.")


if __name__ == "__main__":
    main()
