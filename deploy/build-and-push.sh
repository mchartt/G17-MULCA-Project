#!/usr/bin/env bash
# Builds the MUCA-Server and MULCA images, pushes them to REGISTRY, and
# writes deploy/out/stack.yml with those exact images, ready to paste into
# Swarmpit.
#
#   REGISTRY=ghcr.io/<owner> ./deploy/build-and-push.sh
#
# Log in to the registry first (docker login <registry host>).
#
# Each image is tagged with its own repo's commit, plus "-dirty" when that
# repo has uncommitted changes. The stack uses that tag, not "latest", so
# every deploy names the exact build it runs and an older stack file rolls
# back to an older build.
#
# Optional:
#   MUCA_SERVER_DIR  MUCA-Server checkout (default: ../MUCA-Server beside this repo)
#   PLATFORM         target platform of the swarm's nodes (default: linux/amd64)
#   PUSH=0           build only, nothing pushed

set -euo pipefail

: "${REGISTRY:?Set REGISTRY, e.g. REGISTRY=ghcr.io/<owner>}"
REGISTRY=${REGISTRY%/}

DEPLOY_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MULCA_DIR=$(cd "$DEPLOY_DIR/.." && pwd)
MUCA_SERVER_DIR=$(cd "${MUCA_SERVER_DIR:-$MULCA_DIR/../MUCA-Server}" && pwd)
PLATFORM=${PLATFORM:-linux/amd64}
PUSH=${PUSH:-1}

tag_for() {
    local repo=$1 tag
    tag=$(git -C "$repo" rev-parse --short=12 HEAD)
    if [ -n "$(git -C "$repo" status --porcelain)" ]; then
        tag="$tag-dirty"
    fi
    echo "$tag"
}

MUCA_SERVER_IMAGE="$REGISTRY/muca-server:$(tag_for "$MUCA_SERVER_DIR")"
MULCA_DISCORD_IMAGE="$REGISTRY/mulca-discord:$(tag_for "$MULCA_DIR")"

if [ "$PUSH" = "1" ]; then
    output=(--push)
else
    output=(--load)
fi

echo "==> $MUCA_SERVER_IMAGE"
docker buildx build --platform "$PLATFORM" "${output[@]}" \
    -t "$MUCA_SERVER_IMAGE" \
    "$MUCA_SERVER_DIR"

echo "==> $MULCA_DISCORD_IMAGE"
docker buildx build --platform "$PLATFORM" "${output[@]}" \
    --build-context muca-server="$MUCA_SERVER_DIR" \
    -t "$MULCA_DISCORD_IMAGE" \
    "$MULCA_DIR/prototype"

mkdir -p "$DEPLOY_DIR/out"
sed -e "s|\${MUCA_SERVER_IMAGE}|$MUCA_SERVER_IMAGE|" \
    -e "s|\${MULCA_DISCORD_IMAGE}|$MULCA_DISCORD_IMAGE|" \
    "$DEPLOY_DIR/stack.yml" > "$DEPLOY_DIR/out/stack.yml"

echo
echo "Stack file: $DEPLOY_DIR/out/stack.yml"
if [ "$PUSH" != "1" ]; then
    echo "(PUSH=0: images built locally only, not pushed)"
fi
