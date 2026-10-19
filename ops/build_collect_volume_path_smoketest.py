#!/usr/bin/env python3
"""Validates the OTHER half of this session's collect_artifacts fix: the real
host-side path for files written inside a container to the unnamed `agent_logs`
compose volume (used for /logs/verifier in every real task's docker-compose.yaml).

_pentest_attempt_steps/_isolated_pentest_branch's collect-{label} step reads
/logs/verifier/submission.txt + report.md via sandbox_name mode (VM host, no
container exec) -- but that path only exists INSIDE the `main` container. The
guess made in build_full_pipeline_task.py: since `agent_logs:` is declared with
no `name:` override under a `docker compose -p construction ...` project, Docker's
default local volume driver auto-names it `construction_agent_logs` and stores
its data on the VM host at /var/lib/docker/volumes/construction_agent_logs/_data/.

This test does NOT run full construction -- it boots a tiny 2-line
docker-compose.yaml (one service, one unnamed `agent_logs` volume, same name/
shape as the real template) under the same `-p construction` project name,
writes a marker file into the mounted path from INSIDE the container, then
runs a collect_artifacts step in sandbox_name mode pointed at the guessed host
path to confirm it actually resolves and collects the real file.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

SUFFIX = int(time.time())
SANDBOX_NAME = f"collect-vol-smoke-{SUFFIX}"
AGENT_NAME = "vol-agent"

SETUP_PROMPT = (
    "Run exactly these commands and report the raw output of each, labeled, "
    "nothing else:\n"
    "```\n"
    "mkdir -p /tmp/voltest\n"
    "cat > /tmp/voltest/docker-compose.yaml <<'EOF'\n"
    "services:\n"
    "  main:\n"
    "    image: alpine:3.20\n"
    "    command: sh -c \"mkdir -p /logs/verifier && echo marker-xyz789 > /logs/verifier/submission.txt && echo marker-report-abc456 > /logs/verifier/report.md && sleep infinity\"\n"
    "    volumes:\n"
    "      - agent_logs:/logs/verifier\n"
    "volumes:\n"
    "  agent_logs:\n"
    "EOF\n"
    "cd /tmp/voltest && docker compose -p construction up -d --wait\n"
    "sleep 3\n"
    "docker compose -p construction exec -T main cat /logs/verifier/submission.txt\n"
    "docker volume ls --format '{{.Name}}'\n"
    "docker volume inspect $(docker volume ls --format '{{.Name}}' | grep agent_logs) 2>&1\n"
    "echo done_setup\n"
    "```"
)


def build_steps() -> list[dict]:
    return [
        {
            "id": "deploy-sandbox", "type": "deploy_sandbox",
            "sandbox_name": SANDBOX_NAME, "sandbox_mode": "vm",
            "cpu": 2.0, "memory_mb": 4096, "disk_size_gb": 20,
            "exposed_ports": [8080, 8000],
            "ttl_seconds": 1800,
        },
        {
            "id": "deploy-agent", "type": "install_agent",
            "a2a_agent_id": "claude-code-cli", "agent_name": AGENT_NAME,
            "sandbox_name": SANDBOX_NAME,
            "depends_on": [{"task_step_id": "deploy-sandbox"}],
        },
        {
            "id": "setup-volume", "type": "prompt_agent", "agent_name": AGENT_NAME,
            "depends_on": [{"task_step_id": "deploy-agent"}],
            "timeout_seconds": 300, "max_turns": 10,
            "prompt_id": "setup-volume",
            "model": "anthropic/claude-sonnet-5",
            "prompt": SETUP_PROMPT,
        },
        {
            # Exact shape as the real collect-{label} fix.
            "id": "collect-submission", "type": "collect_artifacts",
            "sandbox_name": SANDBOX_NAME,
            "artifact_paths": [
                "/var/lib/docker/volumes/construction_agent_logs/_data/submission.txt",
                "/var/lib/docker/volumes/construction_agent_logs/_data/report.md",
            ],
            "artifacts_key": "submission-test",
            "depends_on": [{"task_step_id": "setup-volume"}],
            "fail_task_on_error": False,
        },
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--task-id", default=f"test-collect-volume-path-{SUFFIX}")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--litellm-api-key", default=None)
    args = ap.parse_args()

    steps = build_steps()
    print(f"built {len(steps)} steps for {args.task_id!r}")
    for s in steps:
        print(f"  {s['id']:<20} {s['type']}")

    if not args.publish:
        print("\n--publish not given: nothing sent.")
        return

    status, out = hub.publish_task(args.task_id, args.project_id, steps)
    print(f"\npublish -> HTTP {status}")
    if status not in (200, 201):
        raise SystemExit(out)

    if args.run:
        if not args.litellm_api_key:
            raise SystemExit("--run needs --litellm-api-key")
        status, out = hub.run_task(args.task_id, args.project_id, litellm_api_key=args.litellm_api_key)
        print(f"\nrun_task -> HTTP {status}")
        print(out)


if __name__ == "__main__":
    main()
