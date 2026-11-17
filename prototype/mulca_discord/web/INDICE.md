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
| `calendar.py` | ~150 | M5: the read-only iCalendar feed of a group (milestones and open task dates), private revocable link. |
| `app.py` | ~200 | HTTP routes (incl. `POST /api/groups/delete`), the WebSocket and its frame validation, the built frontend and the film. |
| `server_data.py` | ~60 | Deletes a group's data on MUCA-Server (`DELETE /conversation`, `MUCA_ADMIN_TOKEN`). |
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
- Commands carry every M4 command (`planning`, `checkin`, `task`, `why`, `ask`). A frame
  that does not validate still answers its `requestId` with a refusing notice,
  so no button waits forever (tested).
- One lock per group (`WebHub._lock`) around "join the broadcast list + hello"
  and around every broadcast, so a broadcast never reaches a new socket before
  its hello (found by the M3 e2e; regression test in `tests/test_web.py`).
- MUCA-Server down: the chat keeps working, the members see "coordinator
  unavailable", commands answer in words (tested).

## Calendar feed (M5, `calendar.py`)

- `POST /api/calendar` (member token) → a new private link; the old one stops
  working. `GET /api/calendar/<secret>.ics` → the feed, no login (calendar
  apps cannot send one), `Cache-Control: no-store`.
- Built from the last `coordinator_state` the hub received (`web_state` table),
  so a calendar app polling the feed costs no model call.
- One all-day event per dated milestone and per task not done with a date;
  RFC 5545 escaping and line folding (tested).

## Added after M5

- "Helpful" clicks pass through like the other buttons.
- "@coordinator why ..." typed in the chat (`TYPED_WHY` in `hub.py`) is answered
  from the decision log and posted in the chat by Cadence; it is not sent to
  the lab's agent.
- "@coordinator ...?" or "@Cadence ...?" typed in the chat (`typed_question` in
  `hub.py`: a mention plus a question mark) is answered with the server's
  command `ask`, only from the saved tasks, milestones and decisions, with the
  source; when nothing saved answers it, Cadence says so. A mention without a
  question mark still goes to the lab's agent.
- Delete space: the member types the space's name; the hub closes the session,
  asks MUCA-Server to delete the conversation file, then deletes the web side
  and closes every socket of the group with code 4410. If the server part
  fails, nothing is deleted.

## Accounts, linked channels, catch-up (16/11)

- Accounts (`accounts.py`, `account_routes.py`): register, login, logout,
  profile, delete. Passwords are scrypt hashes, tokens are stored hashed, a
  login lasts 30 days, five wrong passwords lock the email for five minutes.
  The account token says who you are; the space token is still one member of
  one space. The profile is saved once and pushed to every space of the user.
- Linked channels: a Discord or Slack channel joins this space with
  `/coordinator link <invite code>`. Plan, decisions and cards are shared;
  each channel keeps its own chat. A message written in another channel
  arrives as `coordinator_mirror` and is shown in the chat with its channel.
- Catch up: the `catchup` command returns the decisions and the other
  channels' messages since the member's last catch-up, read from disk by
  MUCA-Server with no model call.
- Member ids above 2**53-1 (Discord, Slack) go to the browser as strings
  (`browser_safe` in `hub.py`), with a `names` map to show who they are.

## Not verified live

- Everything above is tested offline against a real local MUCA-Server
  (`tests/test_web_accounts.py`, `tests/test_cross_channel.py`). It was not
  run on Render with Azure, the real Discord or the real Slack.
- Linked channels reach each other only when they run against the same
  MUCA-Server process (as `deploy/render/start.sh` does).
