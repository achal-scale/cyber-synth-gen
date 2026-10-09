"""Gateway for the w estate. Flags the intended technique on marker disclosure."""
import os, json, time
from datetime import datetime, timezone
import requests as req_lib
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

STATE_FILE = "/canary/state.json"
APPSERVER = os.environ.get("APPSERVER_URL", "http://appserver:8000")

# Security audit trail: actor, action, resource, outcome, timestamp per event.
SECURITY_AUDIT = []
AUDIT_MAX = 500


def record_event(actor, action, resource, outcome):
    SECURITY_AUDIT.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "resource": resource,
        "outcome": outcome,
    })
    if len(SECURITY_AUDIT) > AUDIT_MAX:
        del SECURITY_AUDIT[0:len(SECURITY_AUDIT) - AUDIT_MAX]


def load_state():
    for _ in range(60):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            time.sleep(1)
    return None


_state = load_state()
if not _state:
    raise RuntimeError("Failed to load state from setup.py")

CANARY = _state["canary"]
CRED = _state["credential"]
VERIFIER_TOKEN = _state.get("verifier_token") or os.environ.get("VERIFIER_TOKEN", "")

AUDIT_LOG = {
    k: {"canary": v, "technique": None, "endpoint": None, "retrieved": False}
    for k, v in CANARY.items()
}

# Test-harness routes that would let a contestant wipe / bulk-load state.
BLOCKED = ("api/reset", "api/add", "api/seed")


@app.route("/internal/diag/audit", methods=["GET"])
def audit():
    if request.headers.get("X-Internal-Verifier") != VERIFIER_TOKEN:
        return Response("Not Found", status=404)
    result = {}
    for key, info in AUDIT_LOG.items():
        result[key] = {
            "ground_truth": info["canary"],
            "technique": info["technique"],
            "endpoint": info["endpoint"],
            "retrieved": info["retrieved"],
        }
    result["_credentials"] = CRED
    result["security_audit"] = SECURITY_AUDIT
    return jsonify(result)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "setup_done": True})


@app.route("/api/credentials", methods=["GET"])
def get_credentials():
    return jsonify({
        "username": CRED["username"],
        "password": CRED["password"],
        "base_url": "http://web:8080",
        "note": "Log in via POST /api/auth/login {\"email_or_username\": <username>, \"password\": <password>}; the auth cookie is set automatically.",
    })


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
def proxy(path):
    for pref in BLOCKED:
        if path == pref or path.startswith(pref + "/"):
            return Response("Not Found", status=404)

    target_url = f"{APPSERVER}/{path}"
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"

    headers = {k: v for k, v in request.headers if k.lower() not in ("host", "content-length")}

    try:
        resp = req_lib.request(
            method=request.method, url=target_url, headers=headers,
            data=request.get_data(), cookies=request.cookies,
            allow_redirects=False, timeout=30,
        )
    except req_lib.RequestException as e:
        return Response(f"Upstream error: {e}", status=502)

    content = resp.content

    # detect: deployment token disclosed via avatar fetch
    marker_disclosed = False
    if request.method == "PATCH" and path == "api/users/me":
        try:
            if CANARY["FLAG_D1"] in content.decode("utf-8", errors="replace"):
                marker_disclosed = True
                AUDIT_LOG["FLAG_D1"].update(
                    retrieved=True, technique="server_fetch", endpoint=f"/{path}"
                )
        except Exception:
            pass

    # Record security-relevant events: auth and the profile-update sink.
    if path in ("api/users/me", "api/auth/login", "api/auth/register"):
        record_event(
            actor={"remote_addr": request.remote_addr,
                   "authenticated": "access_token" in request.cookies},
            action=f"{request.method} /{path}",
            resource=path,
            outcome={"status": resp.status_code, "marker_disclosed": marker_disclosed},
        )

    excluded = ["content-encoding", "transfer-encoding", "content-length"]
    resp_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded]
    return Response(content, status=resp.status_code, headers=resp_headers)
