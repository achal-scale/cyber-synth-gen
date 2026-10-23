#!/usr/bin/env python3
"""Downloads a collect_artifacts step's output from S3 onto the local disk,
recreating the relative directory structure.

A collect_artifacts step's result lives in the completed run's metadata at
context.metadata["collected_artifacts"][step_id]["artifacts"] -- a
{relative_path: s3_uri} dict (confirmed real shape: see the collect_artifacts
smoke tests this session, which produced real "s3://frontier-data-environments/
artifacts/collected_artifacts/..." URIs that `aws s3 cp` can read directly
with the same AWS SSO session already used for hub.py's own auth -- no
separate credential or hub endpoint needed for this).

Usage:
    python3 download_collected_bundle.py <task_id> <workflow_id> <step_id> <dest_dir>

<step_id> may be a glob pattern (e.g. "collect-final-bundle-*") to merge EVERY
matching step's artifacts into one dest_dir in a single call -- required for a
pass@k task, where each label's final bundle is a separate collect_artifacts
step on a separate sandbox. Merging is safe: each label's final bundle is a
full copy of the same /app/task tree loaded from one construction artifact, so
shared files (task.toml, environment/, tests/, ...) are identical across
labels and only trajectories/pass@k_<label>/ differs. Passing one single,
literal step_id (no glob) for a pass@k task's collect-final-bundle-<label>
step produces a zip with mismatched result.json entries for every label but
real evidence (reward.json/trajectory.json/...) for only the one label you
named -- always use the glob form for a pass@k task.
"""
import fnmatch
import json
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

# Full schema this pipeline's own QC expects a shipped bundle to contain --
# cross-checked against construction_step1g_verify.md's own required-files
# list (the pipeline's canonical source of truth for what construction must
# produce) and docs/PENTEST_QC_COPILOT_PROMPT.md / COMPLETE_QA_CHECKLIST.md
# (what QC review checks for). Exact FILES, not just top-level dir presence --
# a dir existing with the wrong/missing files inside it still silently passed
# the old top-level-only check.
_REQUIRED_FILES = [
    "task.toml", "fresh_state.json", "instruction.md", "unintended_findings.json",
    "environment/docker-compose.yaml", "environment/NOTICE.md",
    "environment/agent/Dockerfile", "environment/agent/etc-hosts-seed",
    # operator/ + tests/run_report_rubric.*/judge_prompt_template.md: this
    # pipeline's own grading pattern, not yet migrated to the
    # tests/behavior+tests/report shape other generators use -- see
    # HUB_PIPELINE_PLAN.md. Still the real, required shape for THIS pipeline's
    # output today.
    "operator/behavior-catalog.json", "operator/report-rubric.json",
    "tests/test.sh", "tests/run_report_rubric.sh", "tests/run_report_rubric.py",
    "tests/judge_prompt_template.md", "tests/isolation_test.sh",
    "solution/solve.sh",
]
# PENTEST_QC_COPILOT_PROMPT.md Step 1 / Step 8: oracle (reward=1) and noop
# (reward=0) evidence are mandatory; at least one pass@k trajectory (any
# model) is mandatory too -- QC cannot classify real-fail vs. false-fail, or
# confirm the task is calibrated at all, without it. Checked as prefixes
# since pass@k's own convention is per-model/per-attempt subfolders
# (pass@k_<label>/), not one fixed name.
_REQUIRED_TRAJECTORY_PREFIXES = {
    "trajectories/oracle": True,   # True = hard requirement
    "trajectories/noop": True,
    "trajectories/pass@k": True,  # this download's whole point per this session's ask
}
_EXCLUDE_TOP_LEVEL: set[str] = set()


def _package_zip(dest: Path) -> Path:
    missing_files = [f for f in _REQUIRED_FILES if not (dest / f).is_file()]
    if missing_files:
        print(f"  WARNING: bundle is missing required files: {missing_files}")

    present_rel_dirs = {
        str(p.relative_to(dest).parent).replace("\\", "/")
        for p in dest.rglob("*") if p.is_file()
    }
    for prefix, required in _REQUIRED_TRAJECTORY_PREFIXES.items():
        # Real per-attempt dirs are "prefix_<label>" (underscore-joined, one
        # path segment, e.g. "trajectories/pass@k_deepseek-1") -- NOT
        # "prefix/<label>". A plain startswith(prefix) covers both that form
        # and an exact/subdirectory match; requiring prefix+"/" (an earlier
        # version of this check) would false-report MISSING even when the
        # pass@k_<label> evidence is genuinely present.
        if not any(d.startswith(prefix) for d in present_rel_dirs):
            level = "WARNING" if required else "NOTE"
            print(f"  {level}: no files found under '{prefix}*' -- "
                  f"QC cannot verify this evidence without it.")

    files = sorted(
        p for p in dest.rglob("*")
        if p.is_file() and p.relative_to(dest).parts[0] not in _EXCLUDE_TOP_LEVEL
    )
    zip_path = dest.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=str(f.relative_to(dest)))
    return zip_path


def _write_pass_at_k_result_json(dest: Path, result: dict) -> None:
    """QC (PENTEST_QC_COPILOT_PROMPT.md Step 8) reads a per-trial result.json
    with `exception_info` and the agent's full response content to classify
    real-fail vs. false-fail -- this does NOT exist as a file inside any
    container; it only exists in the hub's own step metadata
    (`result["prompt_responses"]`, keyed by prompt_id, e.g. "pentest-
    deepseek-1"). The judge-rubric step's in-container `cat` commands can
    never produce this -- it has to be pulled here, from the same run_status()
    response already fetched for collected_artifacts."""
    prompt_responses = result.get("prompt_responses", {}) or {}
    written = []
    for prompt_id, response in prompt_responses.items():
        if not prompt_id.startswith("pentest-"):
            continue
        label = prompt_id[len("pentest-"):]
        out_dir = dest / "trajectories" / f"pass@k_{label}"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "result.json").write_text(json.dumps(response, indent=2, default=str))
        written.append(str(out_dir / "result.json"))
    if written:
        print(f"wrote {len(written)} pass@k result.json file(s) from hub step metadata:")
        for w in written:
            print(f"  {w}")
    else:
        print("  NOTE: no 'pentest-*' entries found in this run's prompt_responses -- "
              "no pass@k result.json written. If this run_status is for the pass@k "
              "task (not construction), check prompt_responses' actual key names.")


def main():
    if len(sys.argv) != 5:
        raise SystemExit(f"usage: {sys.argv[0]} <task_id> <workflow_id> <step_id> <dest_dir>")
    task_id, workflow_id, step_id, dest_dir = sys.argv[1:5]

    status, out = hub.run_status(task_id, workflow_id)
    if status != 200:
        raise SystemExit(f"run_status HTTP {status}: {out}")

    result = out.get("result", out)
    collected = result.get("metadata", {}).get("collected_artifacts", {})

    matching_step_ids = [s for s in collected if fnmatch.fnmatchcase(s, step_id)]
    if not matching_step_ids:
        raise SystemExit(
            f"no collected_artifacts step matches '{step_id}'. Available steps: "
            f"{sorted(collected)}"
        )

    artifacts: dict[str, str] = {}
    empty_steps = []
    for sid in sorted(matching_step_ids):
        entry = collected[sid]
        step_artifacts = entry.get("artifacts", {})
        if not step_artifacts:
            empty_steps.append((sid, entry.get("file_artifact_universe")))
            continue
        artifacts.update(step_artifacts)  # later/alphabetically-last label wins on shared paths (identical content)
    if empty_steps:
        print(f"  NOTE: {len(empty_steps)} matched step(s) collected zero files, skipped: {empty_steps}")
    if not artifacts:
        raise SystemExit(f"all {len(matching_step_ids)} matched step(s) collected zero files")

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    print(f"downloading {len(artifacts)} file(s) merged from {len(matching_step_ids)} "
          f"step(s) ({sorted(matching_step_ids)}) into {dest}/")
    for rel_path, s3_uri in artifacts.items():
        local_path = dest / rel_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"  {s3_uri} -> {local_path}")
        subprocess.run(["aws", "s3", "cp", s3_uri, str(local_path)], check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    print(f"done: {len(artifacts)} file(s) in {dest}/")

    _write_pass_at_k_result_json(dest, result)

    zip_path = _package_zip(dest)
    print(f"packaged task zip (Harbor format, files at archive root): {zip_path}")


if __name__ == "__main__":
    main()
