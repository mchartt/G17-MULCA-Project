# Cadence web app (Group Coordinator, M2)

The landing with the scroll film and the three-column console of a group's space.
React 19 + TypeScript + Vite; served by the web adapter `mulca_discord/web/`
(FastAPI in the MULCA client process), which talks to MUCA-Server through the
same `SessionRegistry` Discord uses.

## Run it

```bash
# 1. MUCA-Server with the coordinator on (needs Azure in muca-server/.env)
cd muca-server && MUCA_COORDINATOR_ENABLED=true python run_server.py
# 2. Build the frontend once
cd mulca/prototype/webapp && npm ci && npm run build
# 3. The web adapter (serves the app, the film and the API) -> http://127.0.0.1:8080
cd mulca/prototype && python -m mulca_discord.web
```

Development with hot reload: `npm run dev` (Vite on :5173, forwards `/api`, `/ws`,
`/film` to the adapter on :8080).

## Rehearse without Azure (no cost)

`python webapp/e2e/fake_stack.py` (from `mulca/prototype`) starts an in-process
MUCA-Server with a FAKE model (always the same charter, the agent echoes) plus
the adapter on http://127.0.0.1:8090. Only for tests and rehearsals: never for
the live proof.

## Tests

| What | Command | Result 15/11 |
|---|---|---|
| Card, panel, state reducer (Vitest) | `npm test` | 15 passed |
| Two members end to end (Playwright, fake stack) | `npm run e2e` | 1 passed |
| Accessibility WCAG 2.1 AA (axe-core, fake stack running) | `npm run axe` | 0 violations on landing and console |
| Web adapter (pytest) | `cd .. && python -m pytest tests/test_web.py` | 14 passed, coverage 98 % |

On the Linux shell of the Claude app, Chromium needs `libXdamage.so.1`
(downloaded with `apt-get download libxdamage1`, extracted, `LD_LIBRARY_PATH`).

## Where things are

| Path | What |
|---|---|
| `src/landing/FilmHero.tsx` | Scroll film on a canvas (436 frames, `film/public/desktop`), three beats on index cards, still version with reduced motion |
| `src/landing/Entry.tsx` | Data notice, create a space, join with a code |
| `src/console/` | Console, chat, proposal card, project panel, dialogs, `space.ts` (events -> state) |
| `src/lib/` | HTTP calls, the WebSocket with reconnection, shared types |
| `src/styles/tokens.css` | Colours (with contrast ratios), type scale, radii |
| `film/` | Storyboard, keyframes, clips, `raccorda.py`, frames for the page |
| `docs/` | Build notebook (`stato.md`), brief, design, decisions, screenshots |
