# INDICE — `mulca_discord/web/`

The web app channel of the Group Coordinator ("Cadence"). A FastAPI server in
the MULCA client process: the browser talks to it over HTTP and one WebSocket,
it talks to MUCA-Server through the **same** `SessionRegistry` / `MucaWsClient`
that Discord uses. Nothing here decides or saves project state: MUCA-Server does
(`muca_server/cognition/coordination/`).

Run it alone (no Discord token needed): `python -m mulca_discord.web`.

## How the pieces fit

```
browser ── POST /api/groups, /api/join ──> app.py ──> WebHub.create_group / join_group ──> WebStore (SQLite)
browser ── WS /ws {auth} ───────────────> app.py ──> WebHub.connect (hello: group, members, history)
browser ── {message} ───────────────────> WebHub.post_message ──┐
browser ── {command} / {click} ─────────> WebHub.command / click ┤  SessionRegistry.run (web's own registry)
                                                                 v
                                                            MUCA-Server
            streamed reply ──> ReplyDispatcher ──> WebChannel.send/edit ──> broadcast {message}
            coordinator_*  ──> WebHub._on_coordinator_event ──> broadcast {proposal} / {state}; reply to the asker
```

## Files

| File | Lines | Responsibility |
|---|---|---|
| `store.py` | ~200 | SQLite: groups (invite code, conversation id `web:<code>`), members (name, hashed token), messages. |
| `hub.py` | ~260 | The channel: sockets per group, messages and commands to MUCA-Server, events back. |
| `app.py` | ~150 | HTTP routes, the WebSocket and its frame validation, the built frontend and the film. |
| `__main__.py` | ~60 | Standalone runner, configured by environment variables. |

## Rules it enforces (project instructions, section 10)

- Every request names one member through a token; tokens are stored hashed.
- A socket receives only its own group's events; the answer to a command or a
  click goes only to the member who asked.
- Invite codes: 10 random characters without look-alikes.
- Web member ids are in [1e8, 1e9): never equal to a Discord id (snowflake).
- The coordinator hook is set on the web registry **instance**: Discord's hook
  (on the class, `coordinator/bridge.py`) is untouched (tested).
- Clicks carry every M3 button: `confirm`, `reject`, `take`, `choose` (+ `option`),
  `not_now` (`ClickFrame` in `app.py`, `WebHub.click` in `hub.py`).
- One lock per group (`WebHub._lock`) around "join the broadcast list + hello"
  and around every broadcast, so a broadcast never reaches a new socket before
  its hello (found by the M3 e2e; regression test in `tests/test_web.py`).
- MUCA-Server down: the chat keeps working, the members see "coordinator
  unavailable", commands answer in words (tested).

## Not done here (yet)

- Same conversation for a Discord channel and a web group (multichannel):
  needs A5/A6 verified live (PROGRESS.md).
- Deleting the group's data on MUCA-Server: the protocol has no event for it;
  `WebStore.delete_group` deletes only the web side.
