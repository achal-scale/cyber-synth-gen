#!/usr/bin/env python3
"""Print a finished pass@k run's RESULT: per-branch PASS/FAIL (behavior / flag 0-1)
and the pass rate.

Reads the `verify-{label}` rows out of the run-status `script_results` -- the same
behavior signal drive_full_pipeline uses for the hardening decision. Each verify row
is audit_technique_check.py's return: {"result": true/false, "reason": ..., "technique": ...}.
`result: true` = that solver actually recovered the flag through the intended technique.

NOTE: this is NOT the same as a step's SUCCESS/FAILURE status -- a verify step runs
fine (SUCCESS) and still returns result=false when the solver simply didn't solve.
For pass@k you want the result value, which is what this prints.

Usage (needs VPN + AWS SSO):
  python ops/show_passk_result.py <task_id> <workflow_id> [--model-label deepseek] [--attempts N]
  # workflow_id is what run_task printed, e.g. run-task-can-passk-exp-1-v2-<hex>-0
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402


def _label_num(key: str) -> int:
    try:
        return int(key.rsplit("-", 1)[-1])
    except ValueError:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task_id")
    ap.add_argument("workflow_id")
    ap.add_argument("--model-label", default="deepseek")
    ap.add_argument("--attempts", type=int, default=None,
                    help="expected attempts (denominator); inferred from the results if omitted")
    args = ap.parse_args()

    status, out = hub.run_status(args.task_id, args.workflow_id)
    if status != 200 or not isinstance(out, dict):
        raise SystemExit(f"run-status HTTP {status}: {out}")

    state = out.get("status")
    script_results = out.get("result", {}).get("metadata", {}).get("script_results", {}) or {}
    verify = {k: (v or {}) for k, v in script_results.items() if k.startswith("verify-")}

    n = args.attempts or (max((_label_num(k) for k in verify), default=0))
    print(f"run status: {state}")
    print(f"task: {args.task_id}   workflow: {args.workflow_id}\n")

    passed = solved = errored = missing = 0
    for i in range(1, n + 1):
        key = f"verify-{args.model_label}-{i}"
        row = verify.get(key)
        if row is None:
            tag, detail = "MISSING", "(no verify result -- branch didn't reach verify / infra failure)"
            missing += 1
        elif row.get("result") is True:
            tag, detail = "PASS", f"[{row.get('technique')}] {row.get('reason', '')}"
            solved += 1
        else:
            # result:false is EITHER a genuine non-solve OR the verifier script itself
            # couldn't run (e.g. 'could not reach /internal/diag/audit') -- the reason says which.
            reason = row.get("reason", "")
            if "could not reach" in reason or "not valid JSON" in reason:
                tag, detail = "VERIFY-ERR", reason
                errored += 1
            else:
                tag, detail = "FAIL", reason
        print(f"  {args.model_label}-{i:<3} {tag:<10} {detail[:100]}")

    denom = n or 1
    print(f"\n  solved {solved}/{n}   ->   pass@{n} rate = {solved / denom:.0%}")
    if errored or missing:
        print(f"  (note: {errored} verifier-errored, {missing} missing -- counted as non-solves; "
              f"check those branches before trusting the rate)")
    if not verify:
        print("  (no verify-* results -- run may be incomplete, or verify steps didn't run)")


if __name__ == "__main__":
    main()
