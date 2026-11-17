#!/usr/bin/env bash
# Refreshes the copy of muca-server that Render builds with.
#
# Render builds ONE repository and deploys the branch gitlab-dev. That branch
# holds this project plus a copy of muca-server in vendor/muca-server, which
# the Dockerfile installs. When the server changes, the copy must follow.
#
# Run on a topic branch made from gitlab-dev, then open a pull request into
# gitlab-dev (merging it makes Render deploy):
#   git checkout -b group17/vendor-server origin/gitlab-dev
#   bash deploy/render/update-vendor.sh
#   git push -u origin group17/vendor-server
#
# The server is read from the clone next to this one, at the branch
# group17/coordinator as it is committed there (no .env, no local edits).
# Another clone or branch:  MUCA_SERVER=/path/to/clone MUCA_SERVER_REF=branch
set -euo pipefail
MULCA="$(cd "$(dirname "$0")/../.." && pwd)"
REF="${MUCA_SERVER_REF:-group17/coordinator}"

SERVER="${MUCA_SERVER:-}"
if [ -z "$SERVER" ]; then
  for name in muca-server MUCA-Server G17-MULCA-Server; do
    if [ -d "$MULCA/../$name/.git" ]; then
      SERVER="$MULCA/../$name"
      break
    fi
  done
fi
if [ -z "$SERVER" ] || ! git -C "$SERVER" rev-parse --verify --quiet "$REF^{commit}" >/dev/null; then
  echo "No muca-server clone with $REF next to this one. Set MUCA_SERVER=/path/to/clone." >&2
  exit 1
fi

cd "$MULCA"
if [ -n "$(git status --porcelain -- vendor/muca-server)" ]; then
  echo "vendor/muca-server has changes that are not committed: commit or discard them first." >&2
  exit 1
fi

rm -rf vendor/muca-server
mkdir -p vendor
git -C "$SERVER" archive --format=tar --prefix=vendor/muca-server/ "$REF" | tar -x -C "$MULCA"
git add -A vendor/muca-server

# Many files of the copy on gitlab-dev were committed with Windows line
# endings. A file whose ONLY difference is its line endings is put back as it
# was, so the pull request shows what really changed on the server.
git diff --cached --name-only -z -- vendor/muca-server | while IFS= read -r -d '' file; do
  if git cat-file -e "HEAD:$file" 2>/dev/null && [ -e "$file" ] \
    && [ -z "$(git diff --cached --ignore-cr-at-eol -- "$file")" ]; then
    git reset -q HEAD -- "$file"
    git checkout -- "$file"
  fi
done

SHORT="$(git -C "$SERVER" rev-parse --short "$REF")"
if git diff --cached --quiet -- vendor/muca-server; then
  echo "vendor/muca-server already matches muca-server $SHORT: nothing to commit."
  exit 0
fi
git commit -q -m "Render: muca-server copy at $SHORT" -- vendor/muca-server
echo "Committed: vendor/muca-server is now muca-server $SHORT. Push this branch and open a pull request into gitlab-dev."
