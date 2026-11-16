#!/bin/sh
# Start MUCA-Server, wait until it answers, then the web adapter on $PORT.
# If either process stops, the container stops, and Render restarts it.
set -e
mkdir -p "$MUCA_DB_DIR"

python -m muca_server.run_server &
SERVER=$!

i=0
until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=2)" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 60 ] || ! kill -0 "$SERVER" 2>/dev/null; then
    echo "MUCA-Server did not start" >&2
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
CHANNELS=""
if [ -n "${SLACK_BOT_TOKEN:-}" ] && [ -n "${SLACK_APP_TOKEN:-}" ]; then
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
kill "$SERVER" "$ADAPTER" $CHANNELS 2>/dev/null || true
exit 1
