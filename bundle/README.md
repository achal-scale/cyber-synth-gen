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

## `tasks/gates_smoke.json`: the 3 file-based gates as real TaskSteps

`contract_gate.py`, `oracle_noop_gate.py`, and `sandbox_escape_gate.py` already matched
`run_code`'s `run(input) -> JSON` contract exactly (no changes needed) -- they're packaged as
FileArtifacts (`artifacts/{contract,oracle_noop,sandbox_escape}_gate/script.py`, copied verbatim
from `gate/`) and run as `run_code` steps against the same deployed `dolibarr-b1-sqli` env,
`task_dir`/`rubric_pipeline_path` passed as static `args` (these are author-time-known absolute
paths, unlike `gateway_url` -- no workaround needed here).

`fleet_gate.py` and `stage2_gate.py` aren't wired in yet: both need `trajectories/passk/` data,
which doesn't exist for any task yet (`ops/launch_fleet.py --agent-cmd` still needs a real
agent-harness invocation to produce it -- see its own docstring).

Live-tested (`agent-env run ./bundle --task gates_smoke`): `contract` and `oracle_noop` both
passed; `sandbox_escape` failed with the exact same GATE-STOP message as every standalone run
this session (`batch_01/dolibarr-B1-sqli` is still unhardened) -- confirming the TaskStep wiring
faithfully reproduces the scripts' standalone behavior, not a different code path. The task
correctly failed overall (gate 4 of 4), and teardown still ran automatically even on failure
(independently confirmed via `docker ps` after -- clean).

Hit one unrelated, non-reproducible flake along the way: `LocalSandbox`'s auto-generated work-dir
name is derived from `tempfile.mkdtemp`, whose random suffix charset includes `_` -- one draw
produced a directory name Docker's image-reference parser rejected (`invalid reference format`)
when Compose derived the project name from it (no explicit `-p`, matching `LocalSandbox.terminate()`'s
own convention, which this plugin must not diverge from or teardown would target the wrong
project). A framework-level flake, not something to work around in this plugin; retrying with a
fresh random sandbox_id resolved it immediately.
