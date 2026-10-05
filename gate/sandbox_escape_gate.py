"""Sandbox-escape gate: task-container hardening, statically checked against docker-compose.yaml.

This is the gate synth-gen has no equivalent of — its domain has no offensive-security angle,
so it never needed to prove a sandbox can't be escaped. Ours does, since these tasks hand an
agent real exploit capability against a container on the same host as everything else.

v1 is a STATIC gate: it inspects environment/docker-compose.yaml text for the hardening flags
below. It does not itself attempt a live escape — that's a separate, periodic adversarial audit
against the platform's actual sandbox substrate (container vs. microVM vs. VM-per-rollout),
which this gate cannot prove or disprove from a compose file alone (see root README's note on
synth-gen's agent-env sandbox providers, including the VM-isolated `modal_vm` provider).

Checks, each required on EVERY service in the compose file:
  - no `privileged: true`
  - no docker.sock bind mount (`/var/run/docker.sock`)
  - no `cap_add` entries
  - `cap_drop: [ALL]` present
  - `security_opt` includes `no-new-privileges:true`
  - a memory limit is set (`deploy.resources.limits.memory` or legacy `mem_limit`)

Missing `read_only` rootfs or `pids_limit` are REVIEW, not FAIL, in v1: several of our existing
apps (Dolibarr, GLPI) write to their own filesystem at boot in ways that haven't yet been audited
for a safe tmpfs allowlist, so forcing read-only now would silently break real tasks rather than
harden them. Tightening this from REVIEW to FAIL is a follow-up once that audit is done per-task.

Args: `task_dir`.
"""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


REQUIRED_FAIL_CHECKS = (
    "no_privileged",
    "no_docker_socket",
    "no_cap_add",
    "cap_drop_all",
    "no_new_privileges",
    "memory_limit_set",
)


def _load_compose(task_dir):
    p = Path(task_dir) / "environment" / "docker-compose.yaml"
    if not p.exists():
        raise RuntimeError("GATE-STOP: sandbox-escape gate: no environment/docker-compose.yaml")
    text = p.read_text()
    if yaml is None:
        raise RuntimeError("GATE-CONFIG: sandbox_escape_gate needs PyYAML installed")
    doc = yaml.safe_load(text) or {}
    return doc, text


def _check_service(name, svc):
    fails, reviews = [], []

    if svc.get("privileged") is True:
        fails.append(f"{name}: privileged: true")

    volumes = svc.get("volumes") or []
    for v in volumes:
        v_str = v if isinstance(v, str) else (v.get("source", "") if isinstance(v, dict) else "")
        if "docker.sock" in v_str:
            fails.append(f"{name}: docker.sock bind mount ({v_str})")

    if svc.get("cap_add"):
        fails.append(f"{name}: cap_add set ({svc['cap_add']})")

    cap_drop = svc.get("cap_drop") or []
    if not (isinstance(cap_drop, list) and any(str(c).upper() == "ALL" for c in cap_drop)):
        fails.append(f"{name}: no cap_drop: [ALL]")

    sec_opt = svc.get("security_opt") or []
    if not any("no-new-privileges" in str(s) for s in sec_opt):
        fails.append(f"{name}: no security_opt no-new-privileges:true")

    mem_limit = svc.get("mem_limit")
    deploy_mem = (((svc.get("deploy") or {}).get("resources") or {}).get("limits") or {}).get("memory")
    if not mem_limit and not deploy_mem:
        fails.append(f"{name}: no memory limit set")

    if svc.get("read_only") is not True:
        reviews.append(f"{name}: no read_only rootfs (tmpfs audit pending)")
    pids_limit = svc.get("pids_limit") or (((svc.get("deploy") or {}).get("resources") or {}).get("limits") or {}).get("pids")
    if not pids_limit:
        reviews.append(f"{name}: no pids_limit set")

    return fails, reviews


def run(input):
    args = input.get("args") if isinstance(input, dict) else {}
    task_dir = args.get("task_dir")
    if not task_dir:
        raise ValueError("GATE-CONFIG: sandbox_escape_gate needs task_dir")

    doc, _ = _load_compose(task_dir)
    services = doc.get("services") or {}
    if not services:
        raise RuntimeError("GATE-STOP: sandbox-escape gate: compose file declares no services")

    all_fails, all_reviews = [], []
    for name, svc in services.items():
        fails, reviews = _check_service(name, svc or {})
        all_fails.extend(fails)
        all_reviews.extend(reviews)

    if all_fails:
        raise RuntimeError("GATE-STOP: sandbox-escape gate: " + "; ".join(all_fails))

    return {"status": "pass", "review": all_reviews}


if __name__ == "__main__":
    import json
    print(json.dumps(run({"args": {"task_dir": sys.argv[1]}}), indent=2))
