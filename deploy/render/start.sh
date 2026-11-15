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

# Stop as soon as one of the two exits.
while kill -0 "$SERVER" 2>/dev/null && kill -0 "$ADAPTER" 2>/dev/null; do
  sleep 5
done
echo "one process stopped: exiting so Render restarts the container" >&2
kill "$SERVER" "$ADAPTER" 2>/dev/null || true
exit 1
