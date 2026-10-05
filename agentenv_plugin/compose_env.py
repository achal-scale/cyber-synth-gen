"""ComposeEnv: an agent-env Env that deploys an arbitrary multi-service docker-compose stack.

Why this exists (see CHANGELOG.md): none of agent-env's built-in Env types (MCPServerEnv,
WebsiteEnv, ServiceDBEnv, MultiEnv) accept an arbitrary N-service docker-compose stack -- each
is a fixed shape (WebsiteEnv is exactly frontend+backend; ServiceDBEnv is a rigid Postgres+pgweb+
mcp-sidecar triple for agent-env's own state tracking). Our tasks are 4 services (db, appserver,
a custom grading gateway, the agent) that don't fit any of those shapes.

The real integration point, instead: `LocalSandbox` (providers/sandbox_providers/local_sandbox.py)
is a generic VM-mode sandbox whose work directory can hold an arbitrary `docker-compose.yml` --
its own `terminate()` already runs `docker compose down -v --remove-orphans` in that work dir if
one exists. This Env is a thin wrapper: copy the task's `environment/` directory onto a
LocalSandbox's work dir (as `docker-compose.yml`, the exact name `terminate()` checks for), boot
it, and let agent-env's own sandbox lifecycle (not a bespoke subprocess wrapper) own teardown.

Does NOT serve an agentenv_protocol "environment card" -- these are black-box HTTP pentest tasks
an agent reaches by curl against a published port, not MCP tool-calls, so there is nothing to
reverse-proxy through a gateway or discover via `invoke()`/`supports()`. `DeployedEnv.metadata`
carries the resolved gateway URL instead; callers read it directly, they don't go through the
protocol-card machinery.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import ClassVar, Optional

from agent_env.env.env import DeployedSandboxEnv, Env
from agent_env.providers.sandbox_providers.local_sandbox import LocalSandbox

GATEWAY_SERVICE_NAME = "web"
GATEWAY_CONTAINER_PORT = 8080


class ComposeEnv(Env):
    type: ClassVar[str] = "compose_env"
    description = "Deploys an arbitrary docker-compose.yaml stack via a LocalSandbox, for tasks whose shape doesn't fit WebsiteEnv/MultiEnv"

    def __init__(self, id: str, version: Optional[int], compose_dir: str,
                 gateway_service: str = GATEWAY_SERVICE_NAME,
                 gateway_container_port: int = GATEWAY_CONTAINER_PORT,
                 metadata: Optional[dict] = None):
        super().__init__(id, version, metadata=metadata)
        if not compose_dir:
            raise ValueError("compose_dir cannot be empty")
        self.compose_dir = compose_dir
        self.gateway_service = gateway_service
        self.gateway_container_port = gateway_container_port
        self._sandbox: Optional[LocalSandbox] = None

    def to_dict(self) -> dict:
        base = super().to_dict()
        base["compose_dir"] = self.compose_dir
        base["gateway_service"] = self.gateway_service
        base["gateway_container_port"] = self.gateway_container_port
        return base

    @classmethod
    def from_dict(cls, data: dict) -> "ComposeEnv":
        return cls(
            id=data["id"],
            version=data.get("version"),
            compose_dir=data["compose_dir"],
            gateway_service=data.get("gateway_service", GATEWAY_SERVICE_NAME),
            gateway_container_port=data.get("gateway_container_port", GATEWAY_CONTAINER_PORT),
            metadata=data.get("metadata", {}),
        )

    async def deploy(self, **kwargs) -> DeployedSandboxEnv:
        sandbox = LocalSandbox()
        self._sandbox = sandbox

        src = Path(self.compose_dir)
        dest = sandbox.work_dir
        for item in src.iterdir():
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        # LocalSandbox.terminate() only tears down a compose stack named exactly
        # docker-compose.yml in the work dir -- our tasks use docker-compose.yaml.
        (dest / "docker-compose.yaml").rename(dest / "docker-compose.yml")

        await sandbox.exec_script("cd /app && docker compose up -d --build --wait")

        port_out = await sandbox.exec_script(
            f"cd /app && docker compose port {self.gateway_service} {self.gateway_container_port}"
        )
        host_port = port_out.strip().rsplit(":", 1)[-1]
        gateway_url = f"http://127.0.0.1:{host_port}"

        return DeployedSandboxEnv(
            env_id=self.id,
            env_version=self.version,
            env_provider_type=None,
            sandbox_id=sandbox.sandbox_id,
            sandbox_type="local",
            metadata={**self.metadata, "gateway_url": gateway_url},
        )

    async def terminate(self) -> None:
        """Not part of the Env ABC (teardown is normally generic, via the recorded sandbox_id and
        agent-env's own reaper) -- exposed directly here too since this plugin is being exercised
        standalone, outside a full Task run, for this first proof."""
        if self._sandbox is not None:
            await self._sandbox.terminate()
