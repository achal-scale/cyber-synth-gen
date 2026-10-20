#!/usr/bin/env python3
"""Outer driver: harden -> pass@k -> decide -> loop, for an EXISTING task.

The hub DAG is static, so "if still too easy, harden again" can't live in a task -- this
script is that loop. Each round:

  1. HARDEN: build+publish+run a harden task (build_harden_task) on the current bundle;
     read the hardened bundle artifact id + the oracle gate (verify-oracle).
     - oracle gate false  -> hardening broke solvability -> STOP (invalid round).
  2. PASS@K: build+publish+run a pass@k task (build_passk_extension_task -- the SAME steps
     as the standalone pass@k) on the hardened bundle; read the behavior pass rate.
  3. DECIDE: accept when pass_rate <= --tolerance (oracle already OK); else feed the
     hardened bundle into the next round and loop (up to --max-rounds).

Target (KangKang MVP): pass@k by the weak solver as LOW as possible WHILE solution.sh still
passes (= the oracle gate). Needs a working hub + AWS/VPN; run it yourself (it calls run_task).

Usage:
    python3 ops/drive_hardening_loop.py --project-id <id> \
        --input-bundle-artifact-id <the too-easy task's bundle id> \
        --construction-sandbox-name <orig construction SANDBOX_NAME> \
        --model azure_ai/DeepSeek-V4-Flash --attempts 10 --tolerance 0.30 --max-rounds 3 \
        --litellm-api-key <key>
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402
import build_harden_task as harden_gen  # noqa: E402
import build_passk_extension_task as passk_gen  # noqa: E402
import drive_full_pipeline as drive  # noqa: E402  reuse _run_and_wait / _read_verifier_scores / _pass_rate


def _collected_artifact_id(result: dict, step_id: str) -> str:
    md = (result or {}).get("result", {}).get("metadata", {})
    entry = (md.get("collected_artifacts", {}) or {}).get(step_id) or {}
    aid = (entry.get("file_artifact_universe") or {}).get("id")
    if not aid:
        raise SystemExit(f"no file_artifact_universe id under collected_artifacts[{step_id!r}]; "
                         f"raw collected_artifacts: {md.get('collected_artifacts')}")
    return aid


def _oracle_passed(result: dict) -> bool:
    sr = (result or {}).get("result", {}).get("metadata", {}).get("script_results", {}) or {}
    return (sr.get("verify-oracle") or {}).get("result") is True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--input-bundle-artifact-id", required=True, help="the too-easy task bundle to harden")
    ap.add_argument("--construction-sandbox-name", required=True)
    ap.add_argument("--harden-model", default="anthropic/claude-sonnet-5")
    ap.add_argument("--harden-skill-file", default=str(harden_gen._DEFAULT_SKILL))
    ap.add_argument("--model", required=True, help="pass@k solver, e.g. azure_ai/DeepSeek-V4-Flash")
    ap.add_argument("--model-label", default="deepseek")
    ap.add_argument("--model-effort", default=None)
    ap.add_argument("--harness", default="opencode-cli")
    ap.add_argument("--attempts", type=int, default=10)
    ap.add_argument("--max-turns", type=int, default=100)
    ap.add_argument("--tolerance", type=float, default=0.30, help="accept when pass@k behavior rate <= this")
    ap.add_argument("--behavior-only", dest="behavior_only", action="store_true", default=True,
                    help="drop the judge-rubric R gate (default ON for hardening)")
    ap.add_argument("--with-rubric", dest="behavior_only", action="store_false",
                    help="keep the judge-rubric R gate")
    ap.add_argument("--max-rounds", type=int, default=3)
    ap.add_argument("--id-prefix", default="can-harden")
    ap.add_argument("--litellm-api-key", required=True)
    args = ap.parse_args()

    skill_path = Path(args.harden_skill_file).expanduser()
    if not skill_path.is_file():
        raise SystemExit(f"harden skill not found: {skill_path} (clone scaleapi/cyber-sample-tasks "
                         "or pass --harden-skill-file).")
    skill_text = skill_path.read_text(encoding="utf-8")

    current_bundle = args.input_bundle_artifact_id
    attempt_labels = [f"{args.model_label}-{n}" for n in range(1, args.attempts + 1)]

    for rnd in range(1, args.max_rounds + 1):
        suffix = f"r{rnd}-{int(time.time())}"

        # 1. HARDEN
        harden_task_id = f"{args.id_prefix}-harden-{suffix}"
        print(f"\n=== round {rnd}: HARDEN ({harden_task_id}) input_bundle={current_bundle} ===")
        hsteps = harden_gen.build_steps(current_bundle, args.construction_sandbox_name,
                                        args.harden_model, skill_text,
                                        project_id=args.project_id, sandbox_suffix=suffix)
        st, out = hub.publish_task(harden_task_id, args.project_id, hsteps)
        if st not in (200, 201):
            raise SystemExit(f"harden publish failed: HTTP {st} {out}")
        hres = drive._run_and_wait(harden_task_id, args.project_id, args.litellm_api_key)
        if not _oracle_passed(hres):
            raise SystemExit(f"round {rnd}: ORACLE FAILED -- the hardened task is no longer solvable "
                             f"by solution/solve.sh (verify-oracle != true). Stop and inspect "
                             f"{harden_task_id}; the hardening broke the intended exploit.")
        hardened_bundle = _collected_artifact_id(hres, "collect-hardened-bundle")
        print(f"round {rnd}: hardened bundle = {hardened_bundle}  (oracle OK -- still solvable)")

        # 2. PASS@K on the hardened bundle (identical steps to the standalone pass@k)
        passk_task_id = f"{args.id_prefix}-passk-{suffix}"
        print(f"=== round {rnd}: PASS@{args.attempts} ({passk_task_id}) ===")
        psteps = passk_gen.build_steps(hardened_bundle, args.construction_sandbox_name,
                                       args.model, args.model_label, args.harness, args.model_effort,
                                       attempts=args.attempts, max_turns=args.max_turns,
                                       sandbox_suffix=suffix, project_id=args.project_id,
                                       include_judge_rubric=not args.behavior_only)
        st, out = hub.publish_task(passk_task_id, args.project_id, psteps)
        if st not in (200, 201):
            raise SystemExit(f"passk publish failed: HTTP {st} {out}")
        pres = drive._run_and_wait(passk_task_id, args.project_id, args.litellm_api_key)
        scores = drive._read_verifier_scores(pres, attempt_labels)
        rate = drive._pass_rate(scores, args.model_label, args.attempts)
        print(f"round {rnd}: pass@{args.attempts} = {rate:.0%} (tolerance {args.tolerance:.0%})")

        # 3. DECIDE
        if rate <= args.tolerance:
            print(f"\nACCEPTED at round {rnd}: pass@{args.attempts}={rate:.0%} <= {args.tolerance:.0%} "
                  f"and oracle OK.\n  hardened bundle: {hardened_bundle}\n  harden task: {harden_task_id}"
                  f"\n  pass@k task: {passk_task_id}")
            return
        print(f"round {rnd}: still too easy ({rate:.0%} > {args.tolerance:.0%}); hardening the "
              f"hardened bundle further next round.")
        current_bundle = hardened_bundle

    print(f"\nreached --max-rounds={args.max_rounds} without hitting tolerance. "
          f"Last hardened bundle: {current_bundle} (hand to a human / raise --max-rounds).")


if __name__ == "__main__":
    main()
