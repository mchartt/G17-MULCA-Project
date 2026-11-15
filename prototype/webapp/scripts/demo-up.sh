#!/usr/bin/env bash
# Starts the live demo stack on this laptop, in the right order:
#   1. MUCA-Server with the coordinator on (Azure from muca-server/.env)
#   2. the web adapter serving the built app on http://127.0.0.1:8080
# Stop with Ctrl+C (both stop). For the offline rehearsal use e2e/fake_stack.py.
# Run from the folder that holds muca-server and mulca:  bash mulca/prototype/webapp/scripts/demo-up.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
PY="${PYTHON:-python}"

if [ ! -f "$ROOT/muca-server/.env" ]; then
  echo "muca-server/.env is missing: follow muca-server/docs/coordinator/AZURE_SETUP.md first." >&2
  exit 1
fi
if ! grep -q '^AZURE_OPENAI_ENDPOINT=' "$ROOT/muca-server/.env"; then
  echo "AZURE_OPENAI_ENDPOINT is not in muca-server/.env (see AZURE_SETUP.md)." >&2
  exit 1
fi
if [ ! -f "$ROOT/mulca/prototype/webapp/dist/index.html" ]; then
  echo "Build the app first: cd mulca/prototype/webapp && npm ci && npm run build" >&2
  exit 1
fi

cleanup() { kill "${SERVER:-}" "${ADAPTER:-}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "1/2 MUCA-Server (coordinator on) on :8000"
( cd "$ROOT/muca-server" && MUCA_COORDINATOR_ENABLED=true MUCA_LOG_LEVEL=INFO "$PY" -m muca_server.run_server ) &
SERVER=$!
sleep 4

echo "2/2 Web adapter on http://127.0.0.1:8080"
( cd "$ROOT/mulca/prototype" && MUCA_SERVER_URL=ws://localhost:8000/ "$PY" -m mulca_discord.web ) &
ADAPTER=$!

echo "Ready: open http://127.0.0.1:8080 in two browser windows (DEMO_SCRIPT.md)."
wait
