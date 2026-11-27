#!/bin/sh
# Start MUCA-Server, wait until it answers, then the web adapter on $PORT.
# If either process stops, the container stops, and Render restarts it.
# With CADENCE_SNAPSHOT_URL set, /data is brought back first and saved while
# running (snapshot.py): accounts, spaces and memory survive a restart.
set -e
mkdir -p "$MUCA_DB_DIR"
# Both processes must share this token ("Delete space" removes the server's
# data with it). If Render has none, make one for this container's life.
if [ -z "${MUCA_ADMIN_TOKEN:-}" ]; then
  MUCA_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
  export MUCA_ADMIN_TOKEN
fi

SNAPSHOT=""
if [ -n "${CADENCE_SNAPSHOT_URL:-}" ]; then
  # Before any server opens a file. set -e: if a snapshot exists but cannot
  # be read, stop here, or the next save would replace it with nothing.
  python /app/snapshot.py restore
  python /app/snapshot.py watch &
  SNAPSHOT=$!
fi

# Stop the servers, then let the watcher make its last save and exit.
stop_all() {
  for pid in $SERVER $ADAPTER $CHANNELS; do
    kill "$pid" 2>/dev/null || true
  done
  if [ -n "$SNAPSHOT" ]; then
    kill -TERM "$SNAPSHOT" 2>/dev/null || true
    wait "$SNAPSHOT" 2>/dev/null || true
  fi
}
SERVER=""
ADAPTER=""
CHANNELS=""
# Render sends SIGTERM before it stops or replaces the container.
trap 'stop_all; exit 0' TERM INT

python -m muca_server.run_server &
SERVER=$!

i=0
until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2)" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 60 ] || ! kill -0 "$SERVER" 2>/dev/null; then
    echo "MUCA-Server did not start" >&2
    stop_all
    exit 1
  fi
  sleep 1
done
echo "MUCA-Server is up; starting the web adapter on port ${PORT:-8080}"

python -m mulca_discord.web &
ADAPTER=$!

# The chat channels are optional: each starts only if its tokens are set in
# Render (Environment). They must run here, next to MUCA-Server: linked
# channels see each other's cards and messages through this one server.
# Slack: the app-level token, plus either one workspace's bot token (old setup)
# or the app's OAuth client ("Add to Slack": any number of workspaces).
if [ -n "${SLACK_APP_TOKEN:-}" ] && { [ -n "${SLACK_BOT_TOKEN:-}" ] || [ -n "${SLACK_CLIENT_ID:-}" ]; }; then
  python -m mulca_discord.slack &
  CHANNELS="$CHANNELS $!"
  echo "Slack channel started"
fi
if [ -n "${DISCORD_BOT_TOKEN:-}" ]; then
  MULCA_COORDINATOR_ENABLED=true MULCA_DB_PATH=/data/mulca.db python -m mulca_discord &
  CHANNELS="$CHANNELS $!"
  echo "Discord bot started"
fi

# Stop as soon as the server or the web adapter exits (a chat channel that
# stops is only logged: the web app keeps working).
while kill -0 "$SERVER" 2>/dev/null && kill -0 "$ADAPTER" 2>/dev/null; do
  for pid in $CHANNELS; do
    kill -0 "$pid" 2>/dev/null || echo "a chat channel process ($pid) is not running" >&2
  done
  sleep 5
done
echo "one process stopped: exiting so Render restarts the container" >&2
stop_all
exit 1
