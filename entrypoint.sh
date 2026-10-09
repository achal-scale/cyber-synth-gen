#!/bin/sh
set -e
M=$(head -c 32 /dev/urandom | sha256sum | cut -c1-48)
[ -n "$M" ] || { echo "FATAL: marker generation failed" >&2; exit 1; }
printf "%s" "$M" > /seed/marker
echo "[seed-init] wrote /seed/marker"
