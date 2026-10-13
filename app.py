"""
Gateway / reverse proxy for Dolibarr estate.
Reads canary state from /canary/state.json (written by setup.py at boot),
proxies requests, injects canaries, exposes verifier audit endpoint.
"""
import os, json, secrets, time, base64
import requests as req_lib
from flask import Flask, request, Response, jsonify

app = Flask(__name__)

# ── Load state from setup.py ─────────────────────────────────────
STATE_FILE = "/canary/state.json"

def load_state():
    for _ in range(30):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except:
            time.sleep(1)
    return None

_state = load_state()
if not _state:
    raise RuntimeError("Failed to load state from setup.py")

CANARY = _state["canary"]
EXTERNAL_USER_LOGIN = _state["ext_user_login"]
EXTERNAL_USER_APIKEY = _state["ext_user_apikey"]
ADMIN_APIKEY = _state["admin_apikey"]
VERIFIER_TOKEN = _state["verifier_token"] or os.environ.get("VERIFIER_TOKEN", secrets.token_hex(16))

APPSERVER = "http://appserver"

# Audit log
AUDIT_LOG = {k: {"canary": v, "technique": None, "endpoint": None, "retrieved": False} for k, v in CANARY.items()}


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
    result["_credentials"] = {
        "ext_user_login": EXTERNAL_USER_LOGIN,
        "ext_user_apikey": EXTERNAL_USER_APIKEY,
        "admin_apikey": ADMIN_APIKEY,
    }
    return jsonify(result)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "setup_done": True})


@app.route("/api/credentials", methods=["GET"])
def get_credentials():
    return jsonify({
        "login": EXTERNAL_USER_LOGIN,
        "api_key": EXTERNAL_USER_APIKEY,
        "base_url": "http://web:8080",
    })


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
def proxy(path):
    target_url = f"{APPSERVER}/{path}"
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"

    headers = {k: v for k, v in request.headers if k.lower() not in ("host", "content-length")}

    try:
        resp = req_lib.request(
            method=request.method, url=target_url, headers=headers,
            data=request.get_data(), cookies=request.cookies,
            allow_redirects=False, timeout=20,
        )
    except req_lib.RequestException as e:
        return Response(f"Upstream error: {e}", status=502)

    content = resp.content

    # ── Canary detection/injection ────────────────────────────────

    # TASK 1 (IDOR)
    if "invoices/detail" in path and "invoices/secure" not in path:
        try:
            data = json.loads(content)
            if CANARY["FLAG1"] in str(data.get("note_private", "")):
                AUDIT_LOG["FLAG1"].update(retrieved=True, technique="idor_bola", endpoint=f"/{path}")
        except:
            pass

    # TASK 2 (SQLi)
    if "reports/run" in path and "secure-run" not in path:
        try:
            if CANARY["FLAG2"] in content.decode("utf-8", errors="replace"):
                AUDIT_LOG["FLAG2"].update(retrieved=True, technique="second_order_sqli", endpoint=f"/{path}")
        except:
            pass

    # TASK 3 (SSRF)
    if "links/preview" in path and "secure-preview" not in path and request.method == "POST":
        try:
            if CANARY["FLAG3"] in content.decode("utf-8", errors="replace"):
                AUDIT_LOG["FLAG3"].update(retrieved=True, technique="ssrf", endpoint=f"/{path}")
        except:
            pass

    # TASK 4 (Path traversal)
    if "exports/download" in path and "secure-download" not in path:
        try:
            data = json.loads(content)
            if "content" in data:
                decoded = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                if CANARY["FLAG4"] in decoded:
                    AUDIT_LOG["FLAG4"].update(retrieved=True, technique="path_traversal", endpoint=f"/{path}")
        except:
            pass

    # TASK 5 (Mass assignment)
    if "profile/update" in path and "secure-update" not in path and request.method in ("PUT", "POST"):
        try:
            data = json.loads(content)
            profile = data.get("profile", {})
            if str(profile.get("admin")) == "1":
                data["escalation_token"] = CANARY["FLAG5"]
                content = json.dumps(data).encode()
                AUDIT_LOG["FLAG5"].update(retrieved=True, technique="mass_assignment", endpoint=f"/{path}")
        except:
            pass

    excluded = ["content-encoding", "transfer-encoding", "content-length"]
    resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
    return Response(content, status=resp.status_code, headers=resp_headers)
