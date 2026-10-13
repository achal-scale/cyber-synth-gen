#!/usr/bin/env bash
# Push one local directory (an app's pre-injection source, e.g. something from
# cyber-sample-tasks/fixed_env/<app>/) as a public git branch on
# achal-scale/cyber-synth-gen, and print the ready-to-use --base-context value
# for build_full_pipeline_task.py / drive_full_pipeline.py.
#
# WHY A BRANCH, NOT A FileArtifact: run_docker_container's docker_context_url
# wants a plain http(s) .zip, fetched with an unauthenticated curl -- a public
# GitHub branch's own archive/refs/heads/<branch>.zip URL is exactly that, with
# no Mongo/FileArtifact registration needed at all. The repo must stay public
# for this to work (confirmed earlier this session -- a private repo's zip
# needs an authenticated request run_docker_container's plain curl can't make).
#
# Usage:
#   ops/push_base_context.sh <local_dir> <branch_name> [repo]
#
# Example (cacti, a single-service app with no pre-built gateway):
#   ops/push_base_context.sh \
#     ../cyber-sample-tasks/fixed_env/cacti/cacti \
#     hubctx-base-cacti
#   -> prints: --base-context "cacti=https://github.com/achal-scale/cyber-synth-gen/archive/refs/heads/hubctx-base-cacti.zip"
#
# NOTE on large vendored files: GitHub's hard per-file limit is 100MB (warns at
# 50MB). cacti's vendored tarball is ~18MB, fine. If a future app's directory
# has something larger, this script still pushes it (git handles it), but
# consider Git LFS or a different host if you hit the 100MB wall -- not solved
# here since nothing in this project has needed it yet.
set -euo pipefail

LOCAL_DIR="${1:?usage: push_base_context.sh <local_dir> <branch_name> [repo]}"
BRANCH="${2:?usage: push_base_context.sh <local_dir> <branch_name> [repo]}"
REPO="${3:-achal-scale/cyber-synth-gen}"

[ -d "$LOCAL_DIR" ] || { echo "no such directory: $LOCAL_DIR" >&2; exit 1; }
LOCAL_DIR="$(cd "$LOCAL_DIR" && pwd)"

# Visibility check -- the whole point of this script breaks silently against a
# private repo (push succeeds, the zip URL 404s under an unauthenticated curl
# on the hub side), so fail loudly up front instead.
VISIBILITY="$(gh repo view "$REPO" --json visibility -q .visibility 2>/dev/null || echo "")"
if [ "$VISIBILITY" != "PUBLIC" ]; then
  echo "FATAL: $REPO is not public (visibility=${VISIBILITY:-unknown})." >&2
  echo "run_docker_container's docker_context_url needs an unauthenticated curl to succeed." >&2
  echo "Make it public first: gh repo edit $REPO --visibility public --accept-visibility-change-consequences" >&2
  exit 1
fi

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

echo "cloning $REPO (detached worktree) ..." >&2
git clone --quiet "https://github.com/${REPO}.git" "$SCRATCH/repo"
cd "$SCRATCH/repo"

git checkout --orphan "$BRANCH" >/dev/null 2>&1
git rm -rf . >/dev/null 2>&1 || true
git clean -fdx >/dev/null 2>&1
cp -r "$LOCAL_DIR/." .
git add -A
git commit -q -m "hub docker-context: $BRANCH (from $LOCAL_DIR)"
git push origin "$BRANCH"

URL="https://github.com/${REPO}/archive/refs/heads/${BRANCH}.zip"
echo "" >&2
echo "pushed. verifying the zip URL is actually fetchable (not just pushed) ..." >&2
CODE="$(curl -s -o /dev/null -w '%{http_code}' -L "$URL")"
if [ "$CODE" != "200" ]; then
  echo "WARNING: zip URL returned HTTP $CODE, not 200 -- something is wrong ($URL)" >&2
  exit 1
fi

echo ""
echo "--base-context \"<name>=${URL}\""
