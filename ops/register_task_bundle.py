#!/usr/bin/env python3
"""Register a repo task directory (e.g. cyber-sample-tasks/batch_01/dolibarr-B1-sqli) as a
loadable hub bundle -- a FileArtifactUniverse -- so pass@k / the harden loop can load it via
load_artifact(artifact_id=...).

`FileArtifact.put` is single-file only; a task is a TREE, so this uses
FileArtifactUniverse.put_bundled (bundle-key -> local path), the same universe type that
construction's collect-task-bundle emits. Excludes dev-only / run-output subtrees
(trajectories/, .git/, __pycache__) so the bundle is just the task definition.

Setup (one-time): a venv with agentenvhub_sdk installed FROM scale-pypi (not an editable
source install -- that resolves private deps from public PyPI and fails). See the
install-agentenvhub-sdk skill. Needs an AWS SSO session (prod Mongo/S3). e.g.:
    uv venv ~/.venvs/hubreg
    uv pip install --python ~/.venvs/hubreg/bin/python --default-index "$SCALE_PYPI" agentenvhub-sdk
    aws sso login --profile production-developer
    ~/.venvs/hubreg/bin/python ops/register_task_bundle.py \
        --task-dir ~/cyber-sample-tasks/batch_01/dolibarr-B1-sqli \
        --artifact-id can-dolibarr-b1-sqli-task
"""
import argparse
from pathlib import Path

try:
    import agentenvhub_sdk.bootstrap  # noqa: F401  points AGENT_ENV_CONFIG at the prod stores on import
except ModuleNotFoundError as e:
    raise SystemExit(
        f"{e}\n\nagentenvhub_sdk is required to register against the hub (it wires the prod "
        "S3/Mongo artifact store). Install it from scale-pypi into this python, then retry:\n"
        "  uv pip install --python <this-python> --default-index \"$SCALE_PYPI\" agentenvhub-sdk\n"
        "  aws sso login --profile production-developer\n"
        "(see the install-agentenvhub-sdk skill for $SCALE_PYPI)."
    )

from agent_env.artifact import FileArtifactUniverse  # noqa: E402

# Dev-only / run-output trees that must NOT ship in the loadable task bundle.
_SKIP_DIRS = {"trajectories", ".git", "__pycache__", ".pytest_cache", ".ruff_cache"}


def _bundle_files(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if _SKIP_DIRS & set(rel.parts):
            continue
        files[str(rel)] = p
    return files


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task-dir", required=True, help="repo task directory to register")
    ap.add_argument("--artifact-id", required=True,
                    help="hub artifact id to register under (traceable, e.g. can-dolibarr-b1-sqli-task)")
    ap.add_argument("--dry-run", action="store_true", help="list the bundle files, do NOT upload")
    args = ap.parse_args()

    root = Path(args.task_dir).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")

    files = _bundle_files(root)
    if not files:
        raise SystemExit(f"no files to bundle under {root} (all excluded?)")

    total = sum(p.stat().st_size for p in files.values())
    print(f"task dir : {root}")
    print(f"bundle   : {len(files)} files, {total/1e6:.2f} MB  (excluding {sorted(_SKIP_DIRS)})")
    for rel in list(files)[:40]:
        print(f"  {rel}")
    if len(files) > 40:
        print(f"  ... (+{len(files) - 40} more)")

    # s3_url prefix: mirror agent-env's own `artifact file-artifact-universe put-bundled`
    # CLI (cli/artifact/file_artifact_universe.py) -- s3://<configured-bucket>/file_artifact_universe/<id>/.
    from agent_env.config import get_config
    s3_url = f"s3://{get_config().get_s3_bucket()}/file_artifact_universe/{args.artifact_id}/"
    print(f"s3_url   : {s3_url}")

    if args.dry_run:
        print("\n--dry-run: nothing uploaded.")
        return

    u = FileArtifactUniverse.put_bundled(id=args.artifact_id, files=files, s3_url=s3_url)
    print(f"\nregistered FileArtifactUniverse id={u.id!r}")
    print("Load it in pass@k/harden with --task-bundle-artifact-id / --input-bundle-artifact-id "
          f"{u.id} (and --vchan-volume construction_vchan for a batch_01 single-task bundle).")


if __name__ == "__main__":
    main()
