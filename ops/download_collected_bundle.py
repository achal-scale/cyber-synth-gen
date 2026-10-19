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
"""
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

# Confirmed against new_format_batch/210_12_httpd-c2.zip: files sit at the
# ARCHIVE ROOT (task.toml, instruction_L0.md, environment/, tests/, solution/,
# operator/ all top-level), not nested under a wrapper directory.
_REQUIRED_TOP_LEVEL = ["task.toml", "instruction_L0.md", "environment", "tests", "solution", "operator"]
# Not part of the reference format (construction's own internal oracle/noop QC logs).
_EXCLUDE_TOP_LEVEL = {"trajectories"}


def _package_zip(dest: Path) -> Path:
    missing = [name for name in _REQUIRED_TOP_LEVEL if not (dest / name).exists()]
    if missing:
        print(f"  WARNING: bundle is missing expected top-level entries for a real task zip: {missing}")
    files = sorted(
        p for p in dest.rglob("*")
        if p.is_file() and p.relative_to(dest).parts[0] not in _EXCLUDE_TOP_LEVEL
    )
    zip_path = dest.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, arcname=str(f.relative_to(dest)))
    return zip_path


def main():
    if len(sys.argv) != 5:
        raise SystemExit(f"usage: {sys.argv[0]} <task_id> <workflow_id> <step_id> <dest_dir>")
    task_id, workflow_id, step_id, dest_dir = sys.argv[1:5]

    status, out = hub.run_status(task_id, workflow_id)
    if status != 200:
        raise SystemExit(f"run_status HTTP {status}: {out}")

    result = out.get("result", out)
    collected = result.get("metadata", {}).get("collected_artifacts", {})
    entry = collected.get(step_id)
    if entry is None:
        raise SystemExit(
            f"step '{step_id}' has no collected_artifacts entry. Available steps: "
            f"{sorted(collected)}"
        )
    artifacts = entry.get("artifacts", {})
    if not artifacts:
        raise SystemExit(f"step '{step_id}' collected zero files (universe: {entry.get('file_artifact_universe')})")

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    print(f"downloading {len(artifacts)} file(s) from step '{step_id}' into {dest}/")
    for rel_path, s3_uri in artifacts.items():
        local_path = dest / rel_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"  {s3_uri} -> {local_path}")
        subprocess.run(["aws", "s3", "cp", s3_uri, str(local_path)], check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    print(f"done: {len(artifacts)} file(s) in {dest}/")

    zip_path = _package_zip(dest)
    print(f"packaged task zip (Harbor format, files at archive root): {zip_path}")


if __name__ == "__main__":
    main()
