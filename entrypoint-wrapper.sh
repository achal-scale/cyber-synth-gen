#!/bin/bash
# The FLAG4 (path-traversal) canary is minted by the gateway container's
# setup.py into the shared canary_data volume (/canary/pathtraversal_secret.conf,
# reachable on both appserver and web). It also needs to exist at
# /var/www/flag4.conf on THIS (appserver) container specifically, since that is
# where the vulnerable PHP endpoint's doc_root (/var/www/documents) actually
# lives and where a "../" traversal from it resolves to -- /var/www/flag4.conf
# is outside any volume shared with the gateway, so it must be written here,
# not there.
(
  for i in $(seq 1 90); do
    if [ -f /canary/pathtraversal_secret.conf ]; then
      cp /canary/pathtraversal_secret.conf /var/www/flag4.conf
      echo "[appserver] wrote /var/www/flag4.conf from shared canary"
      break
    fi
    sleep 2
  done
) &

exec docker-run.sh "$@"
