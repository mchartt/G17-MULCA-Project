# INDICE — `mulca_discord/coordinator/`

The Group Coordinator on Discord: the `/coordinator` commands and the
proposal cards with Confirm / Reject buttons. **Off** unless
`MULCA_COORDINATOR_ENABLED` is on (and MUCA-Server runs with
`MUCA_COORDINATOR_ENABLED` too). Nothing here decides or saves anything:
MUCA-Server does (`muca_server/cognition/coordination/`).

## How the pieces fit

```
member: /coordinator kickoff  ──> commands.py CoordinatorGroup
member: clicks Confirm        ──> cards.py CardButton.callback
                                        │
                                        v
                               bridge.py CoordinatorBridge
                                 send_command() / click()
                                        │ the group's ONE session (SessionRegistry.run)
                                        v
                                   MUCA-Server
                                        │ coordinator_proposal / _state / _notice
                                        v
               muca_client.py _handle_raw ─> sessions.py on_coordinator_event
                                        │
                                        v
                               bridge.py on_event()
                    card posted or edited in the channel; answer to the member (only they see it)
```

## Files

| File | Lines | Responsibility |
|---|---|---|
| `__init__.py` | 8 | Exports `install_coordinator`. |
| `commands.py` | 120 | The switch, `install_coordinator`, the `/coordinator` group, the plan embed. |
| `bridge.py` | 184 | Sends commands and clicks to MUCA-Server and routes its answers back. |
| `cards.py` | 137 | How a proposal looks: embed + persistent buttons. |

## `commands.py`

| Name | What it does |
|---|---|
| `coordinator_enabled(env)` | True if `MULCA_COORDINATOR_ENABLED` is `1/true/yes/on`. |
| `install_coordinator(manager, tree, env)` | Off → does nothing, returns None. On → creates the bridge, attaches it to every bot's session registry, registers the card buttons (`add_dynamic_items`, so old cards work after a restart) and adds `/coordinator` to the command tree. |
| `CoordinatorGroup` | `/coordinator`, open to every member of a linked channel. |
| `profile(discipline, skills, weekly_hours)` | Saves your own profile (0–80 hours). |
| `kickoff(text)` | Sends the assignment text; the card appears in the channel. |
| `plan()` | Shows the project state, only to you. |
| `state_embed(state)` | Draws the state: goal, milestones, members, tasks, decisions. |

Every command first answers "thinking…" privately (`defer`), because the
model can take some seconds, then the final answer, also private.

## `bridge.py` — `CoordinatorBridge(manager)`

| Name | What it does |
|---|---|
| `attach()` | Sets `registry.on_coordinator_event` of every bot to `on_event`. |
| `send_command(interaction, command, args)` | Builds a `coordinator_command` with a fresh request id and waits for the answer. |
| `click(interaction, action, proposal_id)` | Builds a `proposal_response`, waits for the notice, tells the member privately what happened. |
| `_send(interaction, request_id, message)` | The common path: finds the channel's link, opens the group's one session with `SessionRegistry.run` (never a second connection), sends the roster first (the server checks clicks against it) and then the message; waits up to 60 s. `retry_once=False`: a command is never sent twice. Any error → None, never an exception. |
| `on_event(session, data)` | From MUCA-Server: a `coordinator_proposal` posts or edits the card; a notice or state with a request id wakes the waiting command; a state nobody waits for (meant for the web app) is ignored. |
| `_show_card(session, proposal)` | Edits the card if this run posted it, otherwise posts it while pending. A Discord error is logged, not raised. |
| `scope_for(bot, link)` | The group's `Scope`, built exactly as `runtime.py` builds it. |
| `answer_text(answer)` | The sentence shown to the member (or "did not answer in time"). |

## `cards.py`

| Name | What it does |
|---|---|
| `CUSTOM_ID`, `CUSTOM_ID_PATTERN` | `coord:<confirm|reject>:<proposal id>`: the button carries everything it needs. |
| `STATUS_WORDS`, `STATUS_COLOURS` | The status is always written in words; the colour only adds to it. |
| `proposal_embed(proposal)` | Title "Coordinator · …", the reason in italics, goal, deliverables, milestones, status and expiry in the footer. Long fields are cut to Discord's limit. |
| `card_view(proposal)` | Confirm and Reject while pending; no buttons once closed. |
| `CardButton` | A `DynamicItem`: discord.py rebuilds it from the custom_id (`from_custom_id`), also after a restart; `callback` hands the click to the bridge. |
| `_bullets`, `_clip` | Small text helpers. |

## Hook points in shared MULCA files

| File | Change |
|---|---|
| `muca_client.py` | `COORDINATOR_EVENTS`, the `on_coordinator_event` callback (one `elif` in `_handle_raw`), and `send_coordinator(message)`. |
| `sessions.py` | `SessionRegistry.on_coordinator_event`, wired to each session's client in `get()`. |
| `__main__.py` | `install_coordinator(manager, tree)` right after `install_commands`. |

## Known limits

- Bots added at runtime with `/mulca bot add` get the coordinator events only
  after a restart (`attach()` runs once at start).
- A card posted before a bot restart still works, but its later status
  changes are posted as a new message only while pending; a closed card from
  a previous run is not edited.
- `kickoff` takes the assignment as text (Discord allows up to 6000
  characters); attachments are not read yet.

Tests: `tests/test_coordinator_discord.py` (21 tests, including one end to
end against a real local MUCA-Server with the coordinator on and a fake model).
