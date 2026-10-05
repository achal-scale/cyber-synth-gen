# bundle/

A real, runnable agent-env bundle proving `ComposeEnv` works through the actual framework —
not just the standalone Python test in `agentenv_plugin/README.md`.

## Prerequisites (one-time, this machine)

```bash
uv tool install agentenv-framework
brew install coreutils   # run_code shells out to the `timeout` coreutil; macOS lacks it natively
```

## Register the env (the real gotcha)

Authoring an env through the bundle itself (`envs/<name>/env.toml`, parallel to how artifacts
and agents work) does NOT work in this release -- it fails with
`writing an env isn't supported yet` (the bundle writer table only implements artifacts, agents,
and evals; confirmed by reading `bundle/materialize.py`'s `_WRITERS` dict). The env has to be
put into the store directly, once, before running the task:

```bash
export PYTHONPATH=/path/to/cyber-synth-gen
/path/to/agentenv-framework/bin/python - <<'PY'
import sys; sys.path.insert(0, ".")
from agentenv_plugin.compose_env import ComposeEnv
ComposeEnv.put(id="dolibarr-b1-sqli",
                compose_dir="/path/to/batch_01/dolibarr-B1-sqli/environment")
PY
```

## Run it

```bash
export PYTHONPATH=/path/to/cyber-synth-gen
export PATH="$(brew --prefix coreutils)/libexec/gnubin:$PATH"
agent-env run ./bundle
```

## What `tasks/compose_smoke.json` does

1. `deploy_env`: deploys the stored `dolibarr-b1-sqli` env via `ComposeEnv` -- a real
   `docker compose up -d --build --wait` against a copy of `batch_01/dolibarr-B1-sqli`'s real
   Dockerfiles/compose, through agent-env's own `LocalSandbox`, not a bespoke subprocess wrapper.
2. `run_code` (`artifacts/verify_script/script.py`): confirms `GET {gateway_url}/health`
   returns `200`.

Teardown is automatic -- `agent-env run` tears down every sandbox it deployed when the run ends
(confirmed independently via `docker ps`/`docker network ls`, not just a clean exit).

## A real framework gap this surfaced, not a bug on our side

`run_code`'s `args` are static/author-time literals (`self.args = args or {}`, confirmed by
reading `run_code.py`) and `results` only holds prior `run_code` steps' JSON outputs
(`context.metadata["script_results"]`) -- **`context.deployed_envs`' metadata (where
`ComposeEnv.deploy()` put `gateway_url`) is never passed into a `run_code` script.** There is no
reference/templating syntax to pull it in either. `script.py` works around this by relocating
the sandbox's work dir itself (globbing `~/.agent-env-sandboxes` for the one holding a
`docker-compose.yml`, since only one sandbox is active in this proof) rather than receiving the
URL from the step that deployed it. A real fix would be either a framework change (pass
`deployed_envs` into `run_code`'s input) or a proper instance-store query by `env_id` instead of
a directory glob -- noted as follow-up, not fixed here.
