#!/usr/bin/env python3
"""Cheap, isolated smoke test for the collect_artifacts/load_artifact fix made
in build_full_pipeline_task.py this session.

Two real bugs were diagnosed (via reading agent_env's own collect_artifacts.py
source + two real completed pipeline runs' qwen trajectories, both of which
found /app/task completely empty on qwen's own isolated sandbox):

  1. `artifact_paths: ["/app/task"]` treats that entry as ONE FILE to
     `stat`+`base64`-read, not a directory to recurse into -- `stat` on a
     directory succeeds, but `base64 < /app/task` then fails ("Is a
     directory"), silently producing zero collected files. Fix: omit
     artifact_paths, set `base_path` instead, so collect_artifacts falls back
     to recursively enumerating every file under base_path.
  2. `agent_name=...` mode makes collect_artifacts run container discovery
     (looks for an "agent-api"/"a2a-agent-*" container), which install_agent
     (host mode) never creates. Fix: `sandbox_name=...` (VM-host mode) instead.

This test does NOT run construction -- it fabricates a small nested directory
tree directly (mimicking /app/task: environment/, tests/, a nested file) on
sandbox A, collects it with the FIXED step shape, loads it onto a SEPARATE
sandbox B (mirroring qwen's own isolated-sandbox load), then has sandbox B's
agent verify every file + the directory structure actually arrived intact.
If this passes, the identical step shape in build_full_pipeline_task.py's
_collect_task_bundle_step()/_isolated_pentest_branch() is proven correct
without paying for a multi-hour real construction run.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

SUFFIX = int(time.time())
SANDBOX_A = f"collect-fix-smoke-a-{SUFFIX}"
SANDBOX_B = f"collect-fix-smoke-b-{SUFFIX}"
AGENT_A = "writer-agent"
AGENT_B = "reader-agent"

WRITE_PROMPT = (
    "Run exactly these commands and report the raw output of each, labeled, "
    "nothing else:\n"
    "```\n"
    "mkdir -p /app/task/environment/nested /app/task/tests\n"
    "echo 'root-level-marker-aaa111' > /app/task/instruction_L0.md\n"
    "echo 'compose-marker-bbb222' > /app/task/environment/docker-compose.yaml\n"
    "echo 'nested-marker-ccc333' > /app/task/environment/nested/deep_file.txt\n"
    "echo 'tests-marker-ddd444' > /app/task/tests/test.sh\n"
    "find /app/task -type f | sort\n"
    "echo done_writing\n"
    "```"
)

READ_PROMPT = (
    "Run exactly these commands and report the raw output of each, labeled, "
    "nothing else -- this confirms whether a separate sandbox's /app/task was "
    "populated by a prior collect+load step:\n"
    "```\n"
    "find /app/task -type f | sort\n"
    "cat /app/task/instruction_L0.md 2>&1\n"
    "cat /app/task/environment/docker-compose.yaml 2>&1\n"
    "cat /app/task/environment/nested/deep_file.txt 2>&1\n"
    "cat /app/task/tests/test.sh 2>&1\n"
    "echo done_reading\n"
    "```"
)


def build_steps() -> list[dict]:
    return [
        {
            "id": "deploy-sandbox-a", "type": "deploy_sandbox",
            "sandbox_name": SANDBOX_A, "sandbox_mode": "vm",
            "cpu": 2.0, "memory_mb": 4096, "disk_size_gb": 20,
            "exposed_ports": [8080, 8000],
            "ttl_seconds": 1800,
        },
        {
            "id": "deploy-agent-a", "type": "install_agent",
            "a2a_agent_id": "claude-code-cli", "agent_name": AGENT_A,
            "sandbox_name": SANDBOX_A,
            "depends_on": [{"task_step_id": "deploy-sandbox-a"}],
        },
        {
            "id": "write-tree", "type": "prompt_agent", "agent_name": AGENT_A,
            "depends_on": [{"task_step_id": "deploy-agent-a"}],
            "timeout_seconds": 300, "max_turns": 10,
            "prompt_id": "write-tree",
            "model": "anthropic/claude-sonnet-5",
            "prompt": WRITE_PROMPT,
        },
        {
            # Exact shape as the real _collect_task_bundle_step() fix: no
            # artifact_paths, base_path + sandbox_name (not agent_name).
            "id": "collect-task-bundle", "type": "collect_artifacts",
            "sandbox_name": SANDBOX_A,
            "base_path": "/app/task",
            "artifacts_key": "task_bundle",
            "depends_on": [{"task_step_id": "write-tree"}],
            "fail_task_on_error": False,
        },
        {
            "id": "deploy-sandbox-b", "type": "deploy_sandbox",
            "sandbox_name": SANDBOX_B, "sandbox_mode": "vm",
            "cpu": 2.0, "memory_mb": 4096, "disk_size_gb": 20,
            "exposed_ports": [8080, 8000],
            "ttl_seconds": 1800,
        },
        {
            "id": "deploy-agent-b", "type": "install_agent",
            "a2a_agent_id": "opencode-cli", "agent_name": AGENT_B,
            "sandbox_name": SANDBOX_B,
            "depends_on": [{"task_step_id": "deploy-sandbox-b"}],
        },
        {
            # Exact shape as the real load-task-bundle-qwen step.
            "id": "load-task-bundle-b", "type": "load_artifact",
            "collected_artifacts_step_id": "collect-task-bundle",
            "sandbox_name": SANDBOX_B,
            "destination_path": "/app/task",
            "depends_on": [
                {"task_step_id": "deploy-agent-b"},
                {"task_step_id": "collect-task-bundle"},
            ],
            "fail_task_on_error": False,
        },
        {
            "id": "read-tree", "type": "prompt_agent", "agent_name": AGENT_B,
            "depends_on": [{"task_step_id": "load-task-bundle-b"}],
            "timeout_seconds": 300, "max_turns": 10,
            "prompt_id": "read-tree",
            "model": "anthropic/claude-sonnet-5",
            "prompt": READ_PROMPT,
            "fail_task_on_error": False,
        },
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--task-id", default=f"test-collect-artifacts-fix-{SUFFIX}")
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
