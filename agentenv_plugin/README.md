# agentenv_plugin

A real, live-tested integration with `scaleapi/agentenv-framework` (installed via
`uv tool install agentenv-framework`, v0.9.1267 at the time of writing) — the actual adoption
step from CHANGELOG.md's "yes, adopt agent-env now" decision, not just scripts inspired by it.

## Why a custom Env, not a built-in one

None of agent-env's built-in `Env` types accept an arbitrary N-service docker-compose stack:
- `WebsiteEnv` is exactly 2 containers (one frontend image, one backend image).
- `ServiceDBEnv` is a rigid Postgres+pgweb+mcp-sidecar triple for agent-env's own state
  tracking, not a general app database.
- `MultiEnv` combines `MCPServerEnv`s (Python servers speaking agent-env's own protocol) and
  `WebsiteEnv`s — still built from those same fixed shapes.

Our tasks are 4 arbitrary services (db, appserver, a custom grading gateway, the agent) — none
speak agent-env's protocol, and the backend doesn't split into a frontend/backend pair.

## The real integration point

`providers/sandbox_providers/local_sandbox.py`'s `LocalSandbox` is a generic VM-mode sandbox
whose work directory can hold an arbitrary `docker-compose.yml` — its own `terminate()` already
runs `docker compose down -v --remove-orphans` in that work dir if one exists. `ComposeEnv`
(`compose_env.py`) is a thin `Env` subclass: copy the task's `environment/` directory onto a
`LocalSandbox`'s work dir (renamed to the exact `docker-compose.yml` `terminate()` checks for),
boot it via `exec_script`, resolve the published gateway port, and return a `DeployedSandboxEnv`
with the gateway URL in `metadata` — nothing here reinvents sandbox lifecycle or teardown.

It does not serve an agentenv_protocol "environment card": these are black-box HTTP pentest
tasks reached by curl against a published port, not MCP tool-calls, so there's nothing to
discover via `invoke()`/`supports()`. Callers read `deployed.metadata["gateway_url"]` directly.

## Live-tested

Deployed `ComposeEnv` against a real copy of `batch_01/dolibarr-B1-sqli/environment` (not a
toy fixture): real `docker compose up -d --build --wait` through `LocalSandbox.exec_script`,
confirmed `GET {gateway_url}/health` returns `200 {"status":"ok"}`, then called `terminate()`
and independently verified via `docker ps`/`docker network ls` (not just trusting a clean
return) that every container and network was actually gone afterward.

## Status — what this does and doesn't prove yet

- **Proven**: the plugin's `deploy()`/`terminate()` logic works against a real task, using
  agent-env's real sandbox machinery (not a bespoke subprocess wrapper).
- **Not yet done**: `ComposeEnv` was exercised directly (constructed and called in a plain
  Python script), not through agent-env's actual registry/config (`[envs] impls = [...]`), nor
  through a real `agent-env run <bundle>` Task. That's the next step to actually running this
  under the framework's DAG, not standalone Python.
- **Not yet done**: wiring our `gate/*.py` scripts as agent-env `TaskStep`s, and
  `ops/launch_fleet.py`'s trial loop as a `run_code`-style step in a real Task graph, per the
  `gate/run_attempt.py` lesson from synth-gen.
