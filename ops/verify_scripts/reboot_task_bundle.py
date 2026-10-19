"""run_code script: reboots an already-built, already-injected, already-QC'd task
bundle (loaded onto this sandbox by a prior load_artifact step at /work/task) --
no re-injection, no re-QC, just `docker compose up`. This is the "rebuild instead
of reattach" half of the pass@5 extension design: context.deployed_sandboxes is
per-run, so a completed construction run's sandbox is gone by the time we decide
(from its result) whether pass@5 is warranted; rebooting the collected bundle on a
fresh sandbox is the alternative to (unconfirmed) sandbox reattachment.

Contract (run_code): `def run(input) -> JSON`.
"""
import subprocess


def _sh(cmd: str, timeout: int) -> tuple[int, str, str]:
    p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def run(input: dict) -> dict:
    args = input.get("args", {})
    task_dir = args.get("task_dir", "/work/task")
    compose_project = args.get("compose_project", "pass5")

    rc, out, err = _sh(
        f"cd {task_dir}/environment && docker compose -p {compose_project} up -d --build --wait",
        timeout=600,
    )
    if rc != 0:
        return {"result": False, "reason": f"docker compose up failed (rc={rc})",
                "stdout": out[-3000:], "stderr": err[-3000:]}

    rc, out, err = _sh(f"cd {task_dir}/environment && docker compose -p {compose_project} ps", timeout=30)
    return {"result": True, "reason": "environment rebooted from collected task bundle", "ps": out}
