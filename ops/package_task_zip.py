#!/usr/bin/env python3
"""Zips a downloaded collect-task-bundle directory into the exact Harbor task
zip format this project's reference tasks use (confirmed against
new_format_batch/210_12_httpd-c2.zip): files at the ARCHIVE ROOT, not nested
under a wrapper directory -- task.toml, instruction.md/instruction_L0.md/
instruction_L1.md/instruction_L2.md, unintended_findings.json, environment/,
tests/, solution/, operator/ all directly at the top level.

Usage:
    python3 package_task_zip.py <bundle_dir> <output_zip_path>
"""
import sys
import zipfile
from pathlib import Path

REQUIRED_TOP_LEVEL = [
    "task.toml", "instruction_L0.md", "environment", "tests", "solution", "operator",
]

# Not part of the reference format (confirmed against
# new_format_batch/210_12_httpd-c2.zip's top-level listing) -- construction's
# own internal oracle/noop QC logs, not a shipped task artifact.
EXCLUDE_TOP_LEVEL = {"trajectories"}


def main():
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} <bundle_dir> <output_zip_path>")
    bundle_dir = Path(sys.argv[1])
    output_zip = Path(sys.argv[2])

    if not bundle_dir.is_dir():
        raise SystemExit(f"{bundle_dir} is not a directory")

    missing = [name for name in REQUIRED_TOP_LEVEL if not (bundle_dir / name).exists()]
    if missing:
        print(f"WARNING: bundle is missing expected top-level entries: {missing}")

    files = sorted(
        p for p in bundle_dir.rglob("*")
        if p.is_file() and p.relative_to(bundle_dir).parts[0] not in EXCLUDE_TOP_LEVEL
    )
    if not files:
        raise SystemExit(f"no files found under {bundle_dir}")

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            rel = f.relative_to(bundle_dir)
            zf.write(f, arcname=str(rel))

    print(f"wrote {len(files)} file(s) to {output_zip}")
    with zipfile.ZipFile(output_zip) as zf:
        names = zf.namelist()
        top_level = sorted({n.split("/")[0] for n in names})
        print(f"top-level entries in zip: {top_level}")


if __name__ == "__main__":
    main()
