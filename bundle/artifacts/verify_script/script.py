"""Verify the deployed ComposeEnv's gateway answers /health.

Known gap (documented in agentenv_plugin/README.md): run_code's `args` is static/author-time
only (confirmed by reading run_code.py: `self.args = args or {}`), and `results` only holds
prior run_code steps' outputs -- context.deployed_envs' metadata (where ComposeEnv.deploy()
put gateway_url) is never passed into a run_code script. There is no framework-level reference
mechanism for this.

Pragmatic fix for this proof: the local sandbox root is a fixed, discoverable location
(~/.agent-env-sandboxes), and only one sandbox is active per test run here -- find the one
holding a docker-compose.yml (LocalSandbox.terminate()'s own marker for "a compose stack lives
here") and read the published port directly. Real fix, for later: have ComposeEnv.deploy() query
agent-env's own env-instance store by env_id instead of a directory glob, or have run_code pass
deployed_envs through -- that's a framework gap, not something to work around twice.
"""
import glob
import os
import subprocess
import urllib.request


def run(input):
    root = os.path.expanduser("~/.agent-env-sandboxes")
    candidates = [
        d for d in glob.glob(f"{root}/agent-env-local-*")
        if os.path.exists(os.path.join(d, "docker-compose.yml"))
    ]
    if not candidates:
        return {"error": "no active compose sandbox found", "root": root,
                 "listdir": os.listdir(root) if os.path.exists(root) else None}
    work_dir = max(candidates, key=os.path.getmtime)

    port_out = subprocess.run(
        ["docker", "compose", "port", "web", "8080"],
        cwd=work_dir, capture_output=True, text=True, check=True,
    ).stdout.strip()
    host_port = port_out.rsplit(":", 1)[-1]
    gateway_url = f"http://127.0.0.1:{host_port}"

    with urllib.request.urlopen(gateway_url + "/health", timeout=10) as resp:
        body = resp.read().decode()
        status = resp.status
    return {"work_dir": work_dir, "gateway_url": gateway_url, "status": status, "body": body}
