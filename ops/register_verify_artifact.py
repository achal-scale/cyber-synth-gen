#!/usr/bin/env python3
"""Register (new versions of) this pass@k run's run_code script artifacts on the hub.

The hub's run_code steps execute the REGISTERED artifact, not the file on disk -- so a
local edit does nothing until you run this. Registers OUR isolated ids (leaving Achal's
shared 'audit-technique-check' untouched):

  - scrub-answer-key          <- ops/verify_scripts/scrub_bundle.py
      deterministic host-side scrub that deletes solution/ (+ operator/ in behavior-only)
      before the solver runs, so the difficulty signal isn't contaminated by a solver
      reading the exploit off disk.
  - audit-technique-check-diag <- ops/verify_scripts/audit_technique_check.py
      the behavior/flag check PLUS an on-failure `docker compose ps`/logs diagnostics block.

Both are resolved UNPINNED by their steps, so the newly-registered versions auto-apply to
the next run.

Setup (one-time): needs agentenvhub_sdk installed (it supplies the prod S3/Mongo store
impls that FileArtifact.put uploads through) + a fresh AWS SSO session. e.g.:
    uv pip install --python ~/.venvs/vmprobe/bin/python -e ~/scaleapi/packages/agentenvhub-sdk
    aws sso login
    ~/.venvs/vmprobe/bin/python ops/register_verify_artifact.py
"""
import argparse
from pathlib import Path

try:
    import agentenvhub_sdk.bootstrap  # noqa: F401  points AGENT_ENV_CONFIG at the prod stores on import
except ModuleNotFoundError as e:
    raise SystemExit(
        f"{e}\n\nagentenvhub_sdk is required to register a FileArtifact (it provides the prod "
        "S3/Mongo store impls). Install it, then retry:\n"
        "  uv pip install --python <this-python> -e ~/scaleapi/packages/agentenvhub-sdk\n"
        "  aws sso login\n"
        "(or use the install-agentenvhub-sdk skill)."
    )

from agent_env.artifact import FileArtifact  # noqa: E402

_SCRIPTS = Path(__file__).parent / "verify_scripts"
_ARTIFACTS = [
    ("scrub-answer-key", _SCRIPTS / "scrub_bundle.py",
     "Deterministic host-side scrub: delete solution/ (+ operator/ in behavior-only) before the solver runs"),
    ("audit-technique-check-diag", _SCRIPTS / "audit_technique_check.py",
     "Audit-technique behavior check + on-failure docker ps/logs diagnostics"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=[a[0] for a in _ARTIFACTS], default=None,
                    help="register just one of the artifacts (default: both)")
    args = ap.parse_args()

    for art_id, path, desc in _ARTIFACTS:
        if args.only and art_id != args.only:
            continue
        a = FileArtifact.put(id=art_id, file_path=str(path), description=desc)
        print(f"registered FileArtifact id={a.id!r} version={a.version}")
    print("Steps resolve these ids unpinned -> the new versions auto-apply to the next run.")


if __name__ == "__main__":
    main()
