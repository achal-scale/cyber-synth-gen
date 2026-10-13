#!/usr/bin/env python3
"""Cheap, fast smoke test of the full-pipeline mechanics -- NO agent/LLM spend.

Boots the already-built, already-verified w-task_2_pii environment (3 containers,
from the hubctx-wpii-* branches), runs the real exploit directly from the VM host
via run_code (no agent needed for this -- oracle_attack_wpii.py replays the exact
solve.py logic), then runs the real app-agnostic verifier
(ops/verify_scripts/audit_technique_check.py) to confirm it correctly reads the
disclosure through /internal/diag/audit.

Purpose: isolate and prove the previously-untested parts (deploy_sandbox +
run_docker_container actually building/running from the hosted zips on real hub
infra, the vchan volume naming convention, run_code(sandbox_name=...) actually
executing on the VM host with docker/curl access) BEFORE spending a real,
expensive construction+pass@1 run (build_full_pipeline_task.py) on something that
might fail for a boring infra reason instead of a real construction/pentest one.

Usage:
    python3 ops/build_smoke_task.py <hub_task_id> --project-id <id> [--publish]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub  # noqa: E402

SANDBOX_NAME = "smoke-vm"
VCHAN_VOLUME = f"{SANDBOX_NAME}-vchan"
SEED_VOLUME = f"{SANDBOX_NAME}-seed"

SEED_INIT_ZIP_URL = "https://github.com/achal-scale/cyber-synth-gen/archive/refs/heads/hubctx-wpii-seed-init.zip"
APPSERVER_ZIP_URL = "https://github.com/achal-scale/cyber-synth-gen/archive/refs/heads/hubctx-wpii-w-backend.zip"
GATEWAY_ZIP_URL = "https://github.com/achal-scale/cyber-synth-gen/archive/refs/heads/hubctx-wpii-gateway.zip"

ORACLE_SCRIPT_ARTIFACT_ID = "oracle-attack-wpii-smoke"
VERIFY_SCRIPT_ARTIFACT_ID = "audit-technique-check"


def _deploy_sandbox_step() -> dict:
    return {
        "id": "deploy-sandbox", "type": "deploy_sandbox",
        "sandbox_name": SANDBOX_NAME, "sandbox_mode": "vm",
        "cpu": 2.0, "memory_mb": 4096, "disk_size_gb": 20,
        "exposed_ports": [8080],
        "ttl_seconds": 1800,
    }


def _run_container_step(step_id, container_name, zip_url, dockerfile_path, env_vars,
                         ports, network, extra_networks, volumes, keep_alive, depends_on_ids):
    return {
        "id": step_id, "type": "run_docker_container",
        "sandbox_name": SANDBOX_NAME,
        "docker_context_url": zip_url,
        "dockerfile_path": dockerfile_path,
        "container_name": container_name,
        "env_vars": env_vars or {},
        "ports": ports or [],
        "network": network,
        "extra_networks": extra_networks or [],
        "volumes": volumes or [],
        "keep_alive_with_base_command": keep_alive,
        "depends_on": [{"task_step_id": d} for d in depends_on_ids],
    }


def _oracle_attack_step() -> dict:
    return {
        "id": "oracle-attack", "type": "run_code",
        "sandbox_name": SANDBOX_NAME,
        "depends_on": [{"task_step_id": "run-web"}],
        "script_artifact_id": ORACLE_SCRIPT_ARTIFACT_ID,
        "result_id": "oracle-attack",
        "timeout_seconds": 30,
        "args": {"target_port": 8080},
    }


def _verify_step() -> dict:
    return {
        "id": "verify", "type": "run_code",
        "sandbox_name": SANDBOX_NAME,
        "depends_on": [{"task_step_id": "oracle-attack"}],
        "script_artifact_id": VERIFY_SCRIPT_ARTIFACT_ID,
        "result_id": "verify",
        "timeout_seconds": 60,
        "args": {"vchan_volume": VCHAN_VOLUME, "target_port": 8080},
    }


def build_steps() -> list[dict]:
    return [
        _deploy_sandbox_step(),
        _run_container_step(
            "run-seed-init", "seed-init", SEED_INIT_ZIP_URL, "cyber-synth-gen-hubctx-wpii-seed-init/Dockerfile",
            env_vars=None, ports=None, network="smoke-backend", extra_networks=None,
            volumes=[f"{SEED_VOLUME}:/seed"], keep_alive=False, depends_on_ids=["deploy-sandbox"],
        ),
        _run_container_step(
            "run-appserver", "appserver", APPSERVER_ZIP_URL, "cyber-synth-gen-hubctx-wpii-w-backend/Dockerfile",
            env_vars={
                "PYTHONPATH": "/app", "PYTHONUNBUFFERED": "1",
                "DATABASE_URL": "sqlite:////data/w.db",
                "SECRET_KEY": "labkey_w_pii_3f8a1c6d9e2b4057a8c1d6e9f2b4057a",
            },
            ports=None, network="smoke-backend", extra_networks=None,
            volumes=None, keep_alive=True, depends_on_ids=["deploy-sandbox"],
        ),
        _run_container_step(
            "run-web", "web", GATEWAY_ZIP_URL, "cyber-synth-gen-hubctx-wpii-gateway/Dockerfile",
            env_vars={"APPSERVER_URL": "http://appserver:8000"},
            ports=[8080], network="smoke-frontend", extra_networks=["smoke-backend"],
            volumes=[f"{SEED_VOLUME}:/seed", f"{VCHAN_VOLUME}:/vchan"], keep_alive=True,
            depends_on_ids=["run-seed-init", "run-appserver"],
        ),
        _oracle_attack_step(),
        _verify_step(),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hub_task_id")
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()

    steps = build_steps()
    print(f"built {len(steps)} steps for {args.hub_task_id!r}")
    for s in steps:
        print(f"  {s['id']:<16} {s['type']}")

    if args.publish:
        status, out = hub.publish_task(args.hub_task_id, args.project_id, steps)
        print(f"\npublish: HTTP {status}")
        print(out)
    else:
        print("\n--publish not given: nothing sent. Re-run with --publish to create it on the hub.")


if __name__ == "__main__":
    main()
