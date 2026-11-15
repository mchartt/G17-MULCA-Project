#!/usr/bin/env bash
# Publish the built static preview (dist/) to Vercel.
#   npm run build && bash scripts/deploy-vercel.sh
# The token is read from webapp/.env.vercel (one line: VERCEL_TOKEN=...), never
# printed and never committed (.env.* is git-ignored). Without the file, the
# Vercel CLI asks you to log in in the browser instead.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE/dist"
if [ -f "$HERE/.env.vercel" ]; then
  TOKEN=$(grep -E '^VERCEL_TOKEN=' "$HERE/.env.vercel" | head -1 | cut -d= -f2- | tr -d '\r" ')
  npx -y vercel@latest deploy --prod --yes --token "$TOKEN" 2>&1 | sed "s/$TOKEN/***/g"
else
  npx -y vercel@latest deploy --prod
fi
