#!/usr/bin/env bash
# Builds the "render" branch: group17/coordinator + a copy of muca-server
# (branch group17/coordinator of the clone next to this one) in vendor/muca-server.
# Render builds one repository; this is how it gets both. Run from mulca/:
#   bash deploy/render/update-branch.sh && git push github render
# Uses a temporary worktree: the files you are working on are not touched.
set -euo pipefail
MULCA="$(cd "$(dirname "$0")/../.." && pwd)"
SERVER="$(cd "$MULCA/../muca-server" && pwd)"
WT="$(mktemp -d)/render"

cd "$MULCA"
git worktree add -f -B render "$WT" group17/coordinator
mkdir -p "$WT/vendor"
# A plain snapshot of the server's committed files (no history, no .env).
git -C "$SERVER" archive --format=tar --prefix=vendor/muca-server/ group17/coordinator | tar -x -C "$WT"
cd "$WT"
git add vendor/muca-server
git commit -q -m "Render: muca-server snapshot $(git -C "$SERVER" rev-parse --short group17/coordinator)" || true
cd "$MULCA"
git worktree remove --force "$WT"
echo "Branch render ready: muca-server $(git -C "$SERVER" rev-parse --short group17/coordinator) in vendor/muca-server"
