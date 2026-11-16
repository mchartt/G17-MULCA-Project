# Cadence web app (Group Coordinator, M2)

The landing with the scroll film and the three-column console of a group's space.
React 19 + TypeScript + Vite; served by the web adapter `mulca_discord/web/`
(FastAPI in the MULCA client process), which talks to MUCA-Server through the
same `SessionRegistry` Discord uses.

## Run it

```bash
# 1. MUCA-Server with the coordinator on (needs Azure in muca-server/.env)
cd muca-server && MUCA_COORDINATOR_ENABLED=true python -m muca_server.run_server
# 2. Build the frontend once
cd mulca/prototype/webapp && npm ci && npm run build
# 3. The web adapter (serves the app, the film and the API) -> http://127.0.0.1:8080
cd mulca/prototype && python -m mulca_discord.web
```

Development with hot reload: `npm run dev` (Vite on :5173, forwards `/api`, `/ws`,
`/film` to the adapter on :8080).

## Online preview (Vercel)

Vercel hosts only the static site (landing, film, interface): MUCA-Server and
the web adapter are long-running processes and stay on the demo laptop. On the
preview the entry says so and keeps the forms disabled (it asks `/api/health`).

```bash
npm run build                      # dist/ with the film and dist/vercel.json (SPA routes)
bash scripts/deploy-vercel.sh      # token from webapp/.env.vercel, or browser login
```

To make the preview talk to a running adapter: build with
`VITE_ADAPTER_URL=https://<adapter address>` and start the adapter with
`MULCA_WEB_ALLOWED_ORIGINS=https://<vercel address>` (CORS, tokens in headers).

## Rehearse without Azure (no cost)

`python webapp/e2e/fake_stack.py` (from `mulca/prototype`) starts an in-process
MUCA-Server with a FAKE model (scripted drafts per card schema, the agent
echoes) and a FAKE intervention agent (a message with "font" fires CS2, one with
"think-aloud" fires CS3; planning, check-in and why get scripted answers built
from the real ids in the request), plus the adapter on http://127.0.0.1:8090. Everything
after the trigger is the real code (rules, validation, proposals, cards). Only for tests and rehearsals: never for
the live proof.

## Tests

| What | Command | Result 15/11 (M3) |
|---|---|---|
| Cards of every kind, Why?, Not now, panel (status, Ask why), state reducer, film titles (Vitest) | `npm test` | 28 passed |
| End to end (Playwright, fake stack): charter; CS2 card + Why? + I'll take it; CS3 choice; Not now; planning + status + check-in + why with source; calendar link, feed and revocation | `npm run e2e` | 6 passed |
| Accessibility WCAG 2.1 AA (axe-core, fake stack running) | `npm run axe` | 0 violations on landing, console with card, proactive card with Why? open, planning dialog, plan with status selects |
| Web adapter (pytest) | `cd .. && python -m pytest tests/test_web.py` | 18 passed |

On the Linux shell of the Claude app, Chromium needs `libXdamage.so.1`
(downloaded with `apt-get download libxdamage1`, extracted, `LD_LIBRARY_PATH`).

## Where things are

| Path | What |
|---|---|
| `src/landing/FilmHero.tsx` | Scroll film on a canvas (436 frames, `film/public/desktop`), three beats on index cards, still version with reduced motion |
| `src/landing/Entry.tsx` | Data notice, create a space, join with a code |
| `src/console/` | Console, chat, proposal card (charter, task_owner, delegation, decision; Why? and Not now on proactive cards), project panel, dialogs, `space.ts` (events -> state) |
| `src/preview/` | Preview screens under `/preview` (Connections, Plan around calendars, Catch up, Reflection): sample data from `sample.ts`, no space, no token, no server; linked from the landing ("Next") and the sidebar |
| `src/lib/` | HTTP calls, the WebSocket with reconnection, shared types |
| `src/styles/tokens.css` | Colours (with contrast ratios), type scale, radii |
| `film/` | Storyboard, keyframes, clips, `raccorda.py`, frames for the page |
| `docs/` | Build notebook (`stato.md`), brief, design, decisions, screenshots |
