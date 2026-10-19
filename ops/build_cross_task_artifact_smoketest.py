#!/usr/bin/env python3
"""Smoke test for the NEW piece the two-pipeline split depends on:
load_artifact's `artifact_id` (cross-task) mode, as now used by
build_passk_extension_task.py / _isolated_pentest_branch's
task_bundle_artifact_id parameter.

Does NOT test real construction or a real pentest (those already proved
correct in today's long runs via the SAME-task collected_artifacts_step_id
mode) -- only the one new wire: does a FileArtifactUniverse collected in task
A actually load correctly via `artifact_id` in a totally SEPARATE task B?

Task A: deploy_sandbox + install_agent, write a small nested file tree under
/app/task, collect it (base_path mode -- the fixed collect_artifacts shape).
Task B (separate hub task, published independently): deploy_sandbox +
install_agent, load_artifact(artifact_id=<A's real collected id>), then
confirm the files landed with correct content.
"""
import sys
import time

sys.path.insert(0, "/Users/achal.gandhi/Downloads/stateful_engineering_qhs/active/_scratch_repos/cyber-synth-gen/ops")
import hub  # noqa: E402

PROJECT_ID = "6a97344cdf04bf9f053a4098"
SUFFIX = int(time.time())
SANDBOX_A = f"xtask-smoke-a-{SUFFIX}"
SANDBOX_B = f"xtask-smoke-b-{SUFFIX}"

WRITE_PROMPT = (
    "Run exactly these commands and report the raw output, labeled, nothing else:\n"
    "```\n"
    "mkdir -p /app/task/environment/nested\n"
    "echo 'root-marker-xtask-aaa' > /app/task/instruction_L0.md\n"
    "echo 'nested-marker-xtask-bbb' > /app/task/environment/nested/deep.txt\n"
    "find /app/task -type f | sort\n"
    "echo done_writing\n"
    "```"
)

READ_PROMPT = (
    "Run exactly these commands and report the raw output, labeled, nothing else "
    "-- this confirms a cross-task artifact_id load actually worked:\n"
    "```\n"
    "find /app/task -type f | sort\n"
    "cat /app/task/instruction_L0.md 2>&1\n"
    "cat /app/task/environment/nested/deep.txt 2>&1\n"
    "echo done_reading\n"
    "```"
)


def build_task_a_steps():
    return [
        {"id": "deploy-sandbox", "type": "deploy_sandbox", "sandbox_name": SANDBOX_A,
         "sandbox_mode": "vm", "cpu": 2.0, "memory_mb": 4096, "disk_size_gb": 20,
         "exposed_ports": [8080, 8000], "ttl_seconds": 1800},
        {"id": "deploy-agent", "type": "install_agent", "a2a_agent_id": "claude-code-cli",
         "agent_name": "writer-agent", "sandbox_name": SANDBOX_A,
         "depends_on": [{"task_step_id": "deploy-sandbox"}]},
        {"id": "write-tree", "type": "prompt_agent", "agent_name": "writer-agent",
         "depends_on": [{"task_step_id": "deploy-agent"}],
         "timeout_seconds": 300, "max_turns": 10, "prompt_id": "write-tree",
         "model": "anthropic/claude-sonnet-5", "prompt": WRITE_PROMPT},
        {"id": "collect-task-bundle", "type": "collect_artifacts",
         "sandbox_name": SANDBOX_A, "base_path": "/app/task",
         "artifacts_key": "task_bundle",
         "depends_on": [{"task_step_id": "write-tree"}], "fail_task_on_error": False},
    ]


def build_task_b_steps(artifact_id: str):
    return [
        {"id": "deploy-sandbox", "type": "deploy_sandbox", "sandbox_name": SANDBOX_B,
         "sandbox_mode": "vm", "cpu": 2.0, "memory_mb": 4096, "disk_size_gb": 20,
         "exposed_ports": [8080, 8000], "ttl_seconds": 1800},
        {"id": "deploy-agent", "type": "install_agent", "a2a_agent_id": "opencode-cli",
         "agent_name": "reader-agent", "sandbox_name": SANDBOX_B,
         "depends_on": [{"task_step_id": "deploy-sandbox"}]},
        {"id": "load-task-bundle", "type": "load_artifact",
         "artifact_id": artifact_id,
         "sandbox_name": SANDBOX_B, "destination_path": "/app/task",
         "depends_on": [{"task_step_id": "deploy-agent"}], "fail_task_on_error": False},
        {"id": "read-tree", "type": "prompt_agent", "agent_name": "reader-agent",
         "depends_on": [{"task_step_id": "load-task-bundle"}],
         "timeout_seconds": 300, "max_turns": 10, "prompt_id": "read-tree",
         "model": "anthropic/claude-sonnet-5", "prompt": READ_PROMPT,
         "fail_task_on_error": False},
    ]


def run_and_wait(task_id, litellm_api_key, timeout_s=900):
    status, out = hub.run_task(task_id, PROJECT_ID, litellm_api_key=litellm_api_key)
    print(f"{task_id}: run_task -> {status}: {out}")
    if status not in (200, 201, 202):
        raise SystemExit(out)
    workflow_id = out["workflow_id"]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rs_status, rs_out = hub.run_status(task_id, workflow_id)
        state = (rs_out or {}).get("status")
        print(f"  {task_id} poll -> {rs_status}, status={state}, msg={(rs_out or {}).get('progress',{}).get('message')}")
        if state in ("COMPLETED", "FAILED", "ERROR", "TIMED_OUT", "CANCELLED", "TERMINATED"):
            return rs_out
        time.sleep(10)
    raise SystemExit(f"{task_id} timed out")


def main():
    import os
    litellm_api_key = os.environ["ANTHROPIC_API_KEY"]

    task_a_id = f"xtask-smoke-a-{SUFFIX}"
    status, out = hub.publish_task(task_a_id, PROJECT_ID, build_task_a_steps())
    print(f"Task A publish -> {status}")
    if status not in (200, 201):
        raise SystemExit(out)
    result_a = run_and_wait(task_a_id, litellm_api_key)

    metadata = result_a.get("result", {}).get("metadata", {})
    entry = metadata.get("collected_artifacts", {}).get("collect-task-bundle") or {}
    universe = entry.get("file_artifact_universe") or {}
    artifact_id = universe.get("id")
    print(f"\nTask A's collect-task-bundle artifact_id: {artifact_id!r}")
    if not artifact_id:
        raise SystemExit(f"Task A produced no artifact id! metadata: {metadata}")

    task_b_id = f"xtask-smoke-b-{SUFFIX}"
    status, out = hub.publish_task(task_b_id, PROJECT_ID, build_task_b_steps(artifact_id))
    print(f"\nTask B publish -> {status}")
    if status not in (200, 201):
        raise SystemExit(out)
    result_b = run_and_wait(task_b_id, litellm_api_key)

    print("\n=== Task B final state ===")
    print("status:", result_b.get("status"))
    for r in result_b.get("result", {}).get("prompt_responses", []):
        if r.get("step_id") == "read-tree":
            print("read-tree response:\n", r.get("response"))


if __name__ == "__main__":
    main()
