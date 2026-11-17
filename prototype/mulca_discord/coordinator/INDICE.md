# INDICE — `mulca_discord/coordinator/`

The Group Coordinator on Discord: the `/coordinator` commands and the
proposal cards with their buttons (Confirm / Reject on the charter; on the
proactive M3 cards also I'll take it, one button per option, Why?, Not now). **Off** unless
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
| `commands.py` | 158 | The switch, `install_coordinator`, the `/coordinator` group, the plan embed. |
| `bridge.py` | 223 | Sends commands and clicks to MUCA-Server and routes its answers back; answers "Why?". |
| `cards.py` | 257 | How a proposal looks: embed + persistent buttons, for every kind. |

## `commands.py`

| Name | What it does |
|---|---|
| `coordinator_enabled(env)` | True if `MULCA_COORDINATOR_ENABLED` is `1/true/yes/on`. |
| `install_coordinator(manager, tree, env)` | Off → does nothing, returns None. On → creates the bridge, attaches it (`attach()`), registers the card buttons on the primary bot (`add_dynamic_items`, so old cards work after a restart) and adds `/coordinator` to the command tree. |
| `CoordinatorGroup` | `/coordinator`, open to every member of a linked channel. |
| `profile(discipline, skills, weekly_hours)` | Saves your own profile (0–80 hours). |
| `kickoff(text)` | Sends the assignment text; the card appears in the channel. |
| `planning(tasks)` | M4: the tasks separated by `;` (Discord has no multi-line option) → a plan card with suggested owners. |
| `checkin()` | M4: "on track" privately, or a check-in card in the channel. |
| `task(task, status)` | M4: the task's number in `/coordinator plan` and its new status (todo, doing, done, blocked). |
| `why(question)` | M4: the answer from the decision log with its source, privately. |
| `ask(question)` | The answer from the saved tasks, milestones and decisions with its sources, privately; "nothing saved" when none answers. |
| `plan()` | Shows the project state, only to you; tasks are numbered for `/coordinator task`. |
| `state_embed(state)` | Draws the state: goal, milestones, members, tasks, decisions. |

Every command first answers "thinking…" privately (`defer`), because the
model can take some seconds, then the final answer, also private.

## `bridge.py` — `CoordinatorBridge(manager)`

| Name | What it does |
|---|---|
| `attach()` | Sets `SessionRegistry.on_coordinator_event` **on the class**, so every bot's registry gets the events, also bots added later with `/mulca bot add`. |
| `_register_buttons(client)` | Registers the card button class on the client of the bot that will post a card (clicks arrive on that bot's client), once per client. |
| `send_command(interaction, command, args)` | Builds a `coordinator_command` with a fresh request id and waits for the answer. |
| `why(interaction, proposal_id)` | "Why?": answers privately from the last copy of the card this run saw (`_proposals`), with no server call; after a restart it says the details are gone and points at the reason on the card. |
| `click(interaction, action, proposal_id, option=)` | Builds a `proposal_response` (with `option` for a decision), waits for the notice, tells the member privately what happened. |
| `_send(interaction, request_id, message)` | The common path: finds the channel's link, registers the buttons on that bot, opens the group's one session with `SessionRegistry.run` (never a second connection), sends the roster first (the server checks clicks against it) and then the message; waits up to 60 s. `retry_once=False`: a command is never sent twice. Any error → None, never an exception. |
| `on_event(session, data)` | From MUCA-Server: a `coordinator_proposal` posts or edits the card; a notice or state with a request id wakes the waiting command; a state nobody waits for (meant for the web app) is ignored. |
| `_show_card(session, proposal)` | Edits the card if this run posted it, otherwise posts it while pending. A Discord error is logged, not raised. |
| `scope_for(bot, link)` | The group's `Scope`, built exactly as `runtime.py` builds it. |
| `answer_text(answer)` | The sentence shown to the member; without an answer in 60 s: "still working, the card appears if it succeeds, no need to try again" (the server also refuses a second kickoff while one runs). |

## `cards.py`

| Name | What it does |
|---|---|
| `CUSTOM_ID`, `CUSTOM_ID_PATTERN` | `coord:<action>:<proposal id>`, action one of confirm, reject, take, not_now, why, choose0–choose2: the button carries everything it needs. |
| `STATUS_WORDS`, `STATUS_COLOURS` | The status is always written in words (including "Not now: silenced for 30 minutes"); the colour only adds to it. |
| `KIND_TITLES`, `STRATEGY_NAMES` | Card titles per kind; the strategy in plain words for "Why?". |
| `proposal_embed(proposal)` | Title "Coordinator · …", the reason in italics, the content of the kind (`_fields`), status and expiry in the footer. A suggested owner is a Discord mention. Long fields are cut to Discord's limit. |
| `card_view(proposal)` | While pending: charter → Confirm, Reject; task_owner → Confirm (only with a suggested owner), I'll take it, Reject; delegation → I'll take it, Reject (never assigns); decision → one button per option, Reject; plan → Confirm, Reject; checkin → one button per option, Reject; blocker → Confirm, Reject. Proactive cards (task_owner, delegation, decision, blocker) add Why? and Not now on a second row. No buttons once closed. |
| `why_text(proposal)` | Strategy, topic and the messages behind the card, as a private message. |
| `CardButton` | A `DynamicItem`: discord.py rebuilds it from the custom_id (`from_custom_id`), also after a restart; `callback` hands "Why?" to `bridge.why` and every other button to `bridge.click`. |
| `split_action(action)` | `choose1` → (`choose`, 1). |
| `_bullets`, `_clip` | Small text helpers. |

## Hook points in shared MULCA files

| File | Change |
|---|---|
| `muca_client.py` | `COORDINATOR_EVENTS`, the `on_coordinator_event` callback (one `elif` in `_handle_raw`), and `send_coordinator(message)`. |
| `sessions.py` | `SessionRegistry.on_coordinator_event`, wired to each session's client in `get()`. |
| `__main__.py` | `install_coordinator(manager, tree)` right after `install_commands`. |

## Known limits

- After a restart, the buttons of cards posted by an **added** bot work again
  only once that bot has run one `/coordinator` command (the primary bot's
  work at once).
- A card posted before a bot restart still works, but its later status
  changes are posted as a new message only while pending; a closed card from
  a previous run is not edited.
- `kickoff` takes the assignment as text (Discord allows up to 6000
  characters); attachments are not read yet.

- "Why?" after a bot restart cannot show the messages (the card copy lives in
  memory); the reason in italics stays on the card.

Tests: `tests/test_coordinator_discord.py` (22 tests, including one end to
end against a real local MUCA-Server with the coordinator on and a fake model)
`tests/test_coordinator_discord_m3.py` (M3 cards and buttons, and one end
to end "choose" against a real local MUCA-Server) and
`tests/test_coordinator_discord_m4.py` (M4 commands and cards).
