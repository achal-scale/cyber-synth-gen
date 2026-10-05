#!/bin/bash
fails=0
if cat /vchan/verifier_token >/dev/null 2>&1; then echo "FAIL: agent read /vchan/verifier_token"; fails=1; else echo "ok: token unreadable by agent"; fi
code=$(curl -s -o /dev/null -w '%{http_code}' "${TARGET:-http://web:8080}/internal/diag/audit")
[ "$code" = "404" ] && echo "ok: diag 404 without token" || { echo "FAIL: diag reachable ($code)"; fails=1; }
if curl -s -o /dev/null --max-time 5 http://appserver/ 2>/dev/null; then echo "FAIL: appserver directly reachable"; fails=1; else echo "ok: appserver not directly reachable"; fi
exit $fails
