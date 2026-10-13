#!/usr/bin/env python3
"""agent-env-hub prod client for cyber-synth-gen.

AUTH. AWS4-signed STS GetCallerIdentity -> POST s2sauth.internal.scale.com/jwt ->
header `x-jwt-assertion: JWT <token>`. Ported from the pattern documented in
`dcueva-scale/synth-gen`'s `ops/hub.py` and its `.claude/skills/agent-env-platform`
reference docs, re-derived here as first-party code (not copied) against this
session's own live probes against the real hub (2026-10-06): a real
`GET /api/v1/tasks?project_id=...` returned 200 with real data, and the full
`GET /api/v1/docs/openapi` spec was fetched and read to confirm every step/artifact
shape referenced throughout this repo.

Two things that read as auth failures but are not (confirmed against the live spec):
  - `X-Agent-Env-Client` is MANDATORY (1-128 chars of [A-Za-z0-9._:@/-]); omitting
    it 400s in a way that reads like a rejected token.
  - The assertion prefix is the literal `JWT `, never `Bearer `.

Uses the default AWS SSO session's credentials (`boto3.Session().get_credentials()`),
exactly as the synth-gen docstring describes: "the default SSO session already
resolves the right role."

WHAT THIS DOES NOT DO. It does not create artifacts (FileArtifact, DockerImageArtifact):
that requires a live `pymongo.MongoClient` to the hub's own MongoDB (confirmed by
reading `agent_env.artifact.artifacts.file.FileArtifact.put()`'s source after
`pip install agentenv-framework`), which is real internal infrastructure access this
repo does not have. See CHANGELOG.md / README.md "Hub pipeline status" for exactly
which step types that blocks (`run_code`'s `script_artifact_id`,
`env_outcome_verifier`'s `file_artifact_id`) and the stand-ins used until it's
unblocked.
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

HUB = os.environ.get("HUB_BASE", "https://agent-env-hub.internal.scale.com")
S2SAUTH = "https://s2sauth.internal.scale.com"
STS_REGION = "us-west-2"
STS_HOST = f"sts.{STS_REGION}.amazonaws.com"
STS_PATH = "/?Action=GetCallerIdentity&Version=2011-06-15"
CLIENT = "cyber-synth-gen"

_TOKEN = None
_TOKEN_EXP = 0.0
_REFRESH_MARGIN = 300  # re-mint this many seconds before expiry, not after


def _token_expiry(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload)).get("exp") or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def mint(force=False):
    """AWS4-signed STS GetCallerIdentity -> s2sauth /jwt -> S2S JWT. Cached until shortly
    before its own `exp`, then re-minted; `force` discards the cache regardless."""
    global _TOKEN, _TOKEN_EXP
    if _TOKEN and not force and time.time() < _TOKEN_EXP - _REFRESH_MARGIN:
        return _TOKEN
    creds = boto3.Session().get_credentials()
    if creds is None:
        sys.exit("No AWS credentials (run: aws sso login, or export temporary creds).")
    creds = creds.get_frozen_credentials()
    url = f"https://{STS_HOST}{STS_PATH}"
    req = AWSRequest(method="GET", url=url, headers={"host": STS_HOST})
    SigV4Auth(creds, "sts", STS_REGION).add_auth(req)
    body = json.dumps({"scopes": [], "stsRequest": {"headers": dict(req.headers), "url": url}}).encode()
    r = urllib.request.Request(f"{S2SAUTH}/jwt", data=body,
                                headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(r, timeout=30) as resp:
        tok = json.load(resp).get("jwt")
    if not tok:
        sys.exit("s2sauth /jwt returned no jwt")
    _TOKEN, _TOKEN_EXP = tok, _token_expiry(tok)
    return tok


def _request(method, path, body, timeout, token):
    data = None
    headers = {"X-Agent-Env-Client": CLIENT, "x-jwt-assertion": f"JWT {token}"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    req = urllib.request.Request(f"{HUB}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def call(method, path, body=None, timeout=60):
    """(status, parsed-json-or-text). Retries once on 401 with a freshly minted token."""
    status, raw = _request(method, path, body, timeout, mint())
    if status == 401:
        status, raw = _request(method, path, body, timeout, mint(force=True))
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw.decode("utf-8", "replace")


def list_tasks(project_id, limit=50, id_substring=None):
    path = f"/api/v1/tasks?project_id={project_id}&limit={limit}"
    if id_substring:
        path += f"&id={id_substring}"
    return call("GET", path)


def get_task(task_id, version=None):
    path = f"/api/v1/tasks/{task_id}"
    if version is not None:
        path += f"?version={version}"
    return call("GET", path)


def publish_task(task_id, project_id, steps):
    """POST /api/v1/tasks -- per the platform's own docs: "Posting an existing `id`
    creates the next version; there is no separate update call. The server assigns
    the version, so omit it." Equivalent to the MCP `create_task` tool, exposed here
    so this repo can publish tasks standalone (no MCP runtime required)."""
    return call("POST", "/api/v1/tasks", {"id": task_id, "project_id": project_id, "steps": steps})


def run_task(task_id, project_id, litellm_api_key=None, litellm_key_id=None, agent_model=None,
             close_vm_on_completion=False, version=None):
    """POST /tasks/{id}/run -- one row. EXPENSIVE: boots real sandboxes and spends real
    LLM budget.

    CONFIRMED against the real openapi schema (RunTaskRequest): the real fields are
    `litellm_api_key` (a real key) or `litellm_key_id`, not `litellm_key_alias` (that
    was this function's earlier, wrong guess -- fixed here). `project_id` is nullable
    in the schema; pass it anyway for clarity. `close_vm_on_completion` defaults to
    False in the real schema (not True, as this function previously guessed).
    """
    if not litellm_api_key and not litellm_key_id:
        raise ValueError("run_task needs litellm_api_key or litellm_key_id")
    body = {"project_id": project_id, "close_vm_on_completion": close_vm_on_completion}
    if litellm_api_key:
        body["litellm_api_key"] = litellm_api_key
    if litellm_key_id:
        body["litellm_key_id"] = litellm_key_id
    if agent_model:
        body["agent_model"] = agent_model
    if version is not None:
        body["version"] = version
    return call("POST", f"/api/v1/tasks/{task_id}/run", body)


def run_status(task_id, run_instance_id):
    return call("GET", f"/api/v1/tasks/{task_id}/run-status?workflow_id={run_instance_id}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: hub.py <METHOD> <PATH> [JSON_BODY]")
    b = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    st, out = call(sys.argv[1], sys.argv[2], b)
    print(f"[{st}]")
    print(json.dumps(out, indent=2)[:6000] if not isinstance(out, str) else out[:6000])
