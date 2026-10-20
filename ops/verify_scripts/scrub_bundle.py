"""Deterministic answer-key scrub for a pass@k solver sandbox.

Runs host-side via a run_code step (scrub-{label}) AFTER the task bundle is loaded to
/app/task and BEFORE the solver boots/attacks. Deletes the pipeline's own answer key so
the untrusted solver can't read the exploit off disk and fake a "solve":

  - /app/task/solution  -- always (never needed post-construction)
  - /app/task/operator   -- only when args.remove_operator is True (behavior-only mode;
                            the judge-rubric step needs operator/report-rubric.json, so it
                            is KEPT whenever the rubric runs)

Why this is a run_code step and not a line in the boot-target prompt: a safety-trained
construction model refuses a destructive `rm -rf` (treats it as prompt-injection) and then
sometimes doesn't boot at all -- which left `main` down and broke verification. run_code
executes this deterministically on the VM host, with no model in the loop.

Contract (run_code): `def run(input) -> JSON`, `input = {"args": {...}, "results": {...}}`.
"""
import os
import shutil


def run(input: dict) -> dict:
    args = input.get("args", {}) or {}
    remove_operator = bool(args.get("remove_operator", False))

    targets = ["/app/task/solution"]
    if remove_operator:
        targets.append("/app/task/operator")

    removed, absent, errors = [], [], []
    for path in targets:
        if not os.path.exists(path):
            absent.append(path)
            continue
        try:
            shutil.rmtree(path)
            removed.append(path)
        except OSError as e:
            errors.append(f"{path}: {type(e).__name__}: {e}")

    # Verify nothing targeted remains readable (the whole point of the step).
    still_present = [p for p in targets if os.path.exists(p)]
    return {
        "result": not still_present and not errors,
        "removed": removed,
        "absent": absent,
        "errors": errors,
        "still_present": still_present,
    }
