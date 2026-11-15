# MULCA prototype (Discord adapter)

The orchestrator/working-memory/intervention-and-main-LLM implementation
originally in this repo (`mulca/`) has been **ported to
[`MUCA-Server`](../../MUCA-Server)** and deleted here — see that repo's
`README.md` for its current status. What's left in this repo is
`mulca_discord/`: a thin Discord client that speaks MUCA-Server's WebSocket
protocol (MUCA-Server's `docs/PROTOCOL.md`) -- text channels, DMs, and a
voice channel per linked text channel -- and holds no cognition logic of its own. See
**"Running it"** below for how to run the two together.

The "Implementation status" section right below is a historical record of
the design work that produced the now-ported implementation; treat any path
it references under `mulca/`, `core/`, or `bot/` as describing MUCA-Server's
`muca_server/cognition/` and `muca_server/agents/`, not anything in this repo.

## Implementation status (accurate as of this section's last edit — check git history if this drifts)

Everything below the line has drifted out of date at various points as design
moved faster than code; this list is the single source of truth for "is X
actually built," superseding any implied status in older prose further down
this file.

**✅ Implemented and working:**
- Core pipeline: orchestrator loop, shared WM, stateful Realtime intervention
  agent (GA API), stateless main LLM, Discord text adapter, episodic log
  (`EpisodicLog`).
- **Channel/instance scoping**: `Orchestrator` keys WM/queue/intervention-agent
  by *scope* (`"group"` for the instance's registered channels, `"dm:<user_id>"`
  per DM-ing user), not by raw Discord `channel_id` — the group's channels
  share one WM/session; each DM gets its own, separate, and is **never**
  written to the persisted episodic log (privacy). Verified via a mocked
  end-to-end run (two different "group" channel ids landing in the same WM,
  two DM users getting fully separate WMs, only group-scope entries reaching
  the log).
- **DM support**: `on_message` now detects a DM (`discord.DMChannel`) and lets
  it through regardless of `MULCA_CHANNEL_IDS`, tagging the event `is_dm=True`
  so the orchestrator routes it to its private scope.
- Trigger variables: Gini index, per-participant counts/shares keyed by
  display name, roster-seeded silent participants (needs Server Members
  Intent enabled to populate fully; skipped entirely for DM scope, where a
  roster has no meaning).
- Strategy system: flat pool (`config/strategies/*.yaml`) + independent
  `ACTIVE_STRATEGY_IDS` selection, `trigger_threshold`, `cooldown_messages`
  (hard orchestrator veto + soft LLM hint).
- Four strategies: `participation_equality`, `respond_when_addressed`,
  `non_offensive` (all active by default), `keep_on_topic` (in the pool, not
  currently active — only relevant to the `consensus_ranking` task).
- Forced `@mention` bypass, display names everywhere (`ConversationEvent.label()`),
  auto-reload for dev (`run_with_reloader`), the Beta→GA Realtime API migration.
- **Management cycle** (BLUEPRINT.md §11): every 8th group-scope message,
  `MainLLM.run_management_cycle()` produces an updated `history_summary`
  (~1,500 char / ~250-300 word target, revising the previous one) +
  `participant_roles_summary`; `wm.history` is then truncated to the last 5
  raw events. Never runs for DM scope. **Moved from the intervention agent to
  the main LLM** after a live quality issue: the intervention agent's
  summaries degraded to topic lists on dense factual content (fine on
  conversational/personal content, laundry reminders survived a cycle
  correctly) — the main LLM is the model actually meant for synthesis.
  Verified via mock: fires exactly once at message 8, truncates correctly,
  and the tricky part — resyncing `RealtimeInterventionLLM._sent_history_count`
  after the underlying list shrinks, via `on_history_truncated()` (still
  needed even though that class no longer produces the summary, since it
  still incrementally pushes new history for its own `decide()` judgment) —
  confirmed not to break.
- **`provide_summary` strategy** (BLUEPRINT.md §12): fires when someone
  directly asks for a recap. Orchestrator retrieves the most recent
  `SUMMARY_RETRIEVAL_LIMIT` (50) `EpisodicLog` rows for the channel
  (recency-window, not relevance-ranked — deliberately not a real RAG
  pipeline), excluding `management_cycle` rows, into a transient
  `wm.retrieved_context` field the main LLM reads only on this turn. Verified
  against both a mock and a real SQLite round-trip (channel filtering and
  management_cycle exclusion both confirmed). DM scope silently retrieves
  nothing, by design (DMs are never logged). "Today's session" vs. "everything"
  scoping (§12) is **not implemented** — always fetches the same fixed window
  regardless of phrasing.
- **`recall_detail` merged into `respond_when_addressed`**: retrieval need is
  now an orthogonal signal (`needs_history`, `needs_web_search` — the latter
  unused, no web search capability exists, captured for visibility only), not
  a separate strategy — avoids one new strategy per retrieval-source
  combination as more sources get added later.
- **Real `@mention` no longer bypasses the intervention agent** — folded into
  `respond_when_addressed`'s judged trigger instead, since the forced bypass
  was skipping the *retrieval-need* judgment too (an @mentioned question
  needing history got a worse answer than the same question unmentioned).
  Latency cost of always asking confirmed acceptable in testing.
  `forced_intervention.py` now defines one rule instead: literal `@mainllm`
  text, a deliberate debug/testing bypass to verify the main LLM/dispatch
  path independent of intervention-agent judgment.

**✅ Also implemented:**
- **Startup/shutdown persistence** (§11.1): `WorkingMemorySnapshot` model +
  migration; saved on clean shutdown (`Ctrl+C` — discord.py returns from
  `client.run()` rather than raising), loaded on the next boot before any
  message can arrive. Requires `MULCA_CHANNEL_IDS` set (persistence needs a
  stable key; silently disabled otherwise). Verified round-trip against an
  isolated test DB (never the live one). The intervention agent's own session
  now also receives the restored summary at `connect()` time (fixed a gap
  where only the main LLM saw it) — verified via mock.
  **Gotcha found during live testing, now fixed:** `run_discord_bot` used to
  run under Django's autoreload utility by default. On Windows, the reloader
  runs `run_bot()` in a child subprocess, and Ctrl+C kills that child before
  `run_bot()`'s own shutdown-save code ever executes — confirmed live (the
  save's own debug print never appeared, and a restart afterward correctly
  showed "no snapshot found"). Fixed by making autoreload opt-in
  (`run_discord_bot --autoreload`) instead of the default; plain
  `run_discord_bot` now runs in-process, where Ctrl+C reaches the shutdown
  code directly. **Not yet re-verified end-to-end with the fix in place** —
  next live test should confirm a save+reload round trip actually completes
  with the new default.
- **CoALA memory-type naming** (§4): `experience_memory` (`bot/experience_memory.py`,
  a thin wrapper around `EpisodicLog` — `log()`/`recall_recent()`, replacing
  scattered direct ORM calls), `knowledge_memory` (`task_knowledge`, unchanged),
  `identity_memory` (persona + `participant_roles_summary`, unchanged),
  `skills_memory` (`StrategyStore`, unchanged, name itself not renamed). Purely
  a naming/consolidation pass except for the `experience_memory` wrapper —
  verified against an isolated test DB.

**📝 Designed in BLUEPRINT.md — NOT implemented (queued):**
- A management cycle for `EpisodicLog` itself (tidying the long-term store,
  not just WM) — a new idea from live testing, not designed in detail yet.
- Audio, entirely (§6, §10.2–§10.4) — no `AudioChannelAdapter`, no VAD, no
  turntaking/floor-claim policy, no self-interrupt reflex. Purely a
  documented seam so far. *(Since built, on MUCA-Server's Unity-derived
  turn taking: see "Voice" below.)*
- Strategy YAML schema validation at boot (§7.5) — not built.
- `main.tools_description` tool-calling loop — still a placeholder, no
  tool-calling exists (§3).
- Web search feeding `knowledge_memory` (§4) — `needs_web_search` is already captured on every intervention decision for
  visibility, but nothing acts on it yet.

## Intervention agent: stateful now, not one-shot (BLUEPRINT.md §10.1)

`core/realtime_intervention.py::RealtimeInterventionLLM` replaces the original
stateless one-shot-call version (BLUEPRINT.md §1's original design). One
persistent OpenAI Realtime session per scope (`"group"`, or `"dm:<user_id>"`
— see the "Channel/instance scoping" entry above), created and connected
lazily on first use (`Orchestrator._intervention_agent_for`) — not shared
across scopes, since a session accumulates its own conversational memory and
sharing it would conflate unrelated conversations. Persona, task knowledge,
and the strategy catalog are sent once at connect time, not resent on every
message; each `decide(wm)` call only pushes the history items the session
hasn't already seen. Decisions arrive as a tool call
(`signal_intervention(...)`) rather than a forced-null JSON schema — no tool
call for a given turn means "do nothing."

Still true as originally scoped: text only, one bounded request/response per
incoming message (send new items, call `response.create`, wait for that
turn's `response.done`). Does **not** implement §10.2 (self-interrupt
bypassing the queue) or §10.3 (own VAD tap) — those are audio-phase, not
reached yet. Uses the GA Realtime API (`client.realtime.connect`, model
`gpt-realtime`) — confirmed live, see the Beta→GA migration note in
`realtime_intervention.py`'s module docstring.

## Running it

Two processes, two repos: MUCA-Server (the cognition server) and this repo's
`mulca_discord` (the Discord client of it).

**1. MUCA-Server** (`../../MUCA-Server`), in its own terminal:

```bash
cd ../../MUCA-Server
pip install -e ".[server,openai,storage,dev]"

# .env in MUCA-Server/, not this repo:
#   OPENAI_API_KEY=...
#   MUCA_DB_DIR=...            # optional; default MUCA-Server/data/
#   MUCA_SERVER_HOST=0.0.0.0   # optional, this is the default
#   MUCA_SERVER_PORT=8000      # optional, this is the default

python -m muca_server.run_server
```

`run_server.py` is the composition root: it's what currently hardcodes the
active task (`general_moderation`) and strategy set — see that file to change
either. Memory (working-memory snapshots, the episodic log) persists there,
one SQLite file per conversation, e.g. `data/channel_1555669595581456537.db`.

**2. This adapter**, in a second terminal:

```bash
pip install -r requirements-dev.txt   # includes -e ../../MUCA-Server

cp .env.example .env
# fill in DISCORD_BOT_TOKEN
# MUCA_SERVER_URL=ws://localhost:8000/   -- optional, this is the default
# MUCA_LOG_LEVEL=INFO                    -- optional; default is DEBUG (the
#                                            `mulca_discord` logger tree only,
#                                            not discord.py/websockets' own
#                                            internals), for the [voice-turn]
#                                            diagnostic lines in voice/bridge.py

python -m mulca_discord
```

Which channels the bot answers in is set from Discord, not in code or a
config file: `/mulca link` (Manage Server) links a text channel, optionally
with one voice channel, to the bot. A link's memory belongs to its text
channel (`channel:<id>` on MUCA-Server), so it survives renaming the channel,
changing its voice channel, and unlinking and linking it again. Who takes part
is whoever can see the channel. Links are kept in a small SQLite file
(`MULCA_DB_PATH`, default `data/mulca.db`). Channels that aren't linked are
ignored.

DMs to MULCA are **off by default**: a DM gets a short "I don't take direct
messages" reply. An admin turns them on per linked channel (`/mulca dms`, or
`dms: True` when linking). Then whoever can see that channel may DM the bot
that serves it, privately, and the DM may read that channel's group memory
(the DM-enabled channel they last spoke in, if several). Nobody else can.

The bot needs the "Message Content" and "Server Members" privileged intents
enabled in the Discord developer portal (`discord_client.py` requests
`intents.message_content = True` and `intents.members = True`, the latter for
the roster lookup that seeds silent participants). For voice it also needs
the Connect and Speak permissions in the linked voice channel.

If MUCA-Server restarts, the bot reconnects on the next message (or voice
tick) and the server restores the conversation's memory. The same happens
every hour on its own: OpenAI ends each Realtime connection after 60 minutes,
MUCA-Server then saves the memory and closes that session (code 1012), and
the bot opens a fresh one.

## Slash commands

The bot registers these in every server it's in when it starts (instantly,
per server):

| Command | Who | What |
|---|---|---|
| `/restart` | Anyone, in a channel MULCA serves | Restarts that channel's MULCA: fresh OpenAI connections, same memory. At most once per 30 s per channel. |
| `/mulca status` | Manage Server | Every MULCA bot in this server: online, paused, its channels, its sessions, missing permissions. Only you see the reply. |
| `/mulca restart [bot]` | Manage Server | `/restart` for every channel and DM of one bot, or of all (default). |
| `/mulca stop [bot]` | Manage Server | MULCA leaves voice and stops answering, but stays online so `/mulca start` works. Still stopped after a restart or redeploy. |
| `/mulca start [bot]` | Manage Server | Undoes `/mulca stop`. |
| `/mulca link [text] [voice] [bot] [transcripts] [dms]` | Manage Server | Makes MULCA serve a text channel (default: this one), and optionally a voice channel with it. Linking a linked channel again updates it (`dms` left out keeps its DM setting). One voice channel per bot per server. |
| `/mulca dms enabled [channel]` | Manage Server | Lets the people who can see a linked channel DM MULCA (`True`), or stops them (`False`). Off by default. |
| `/mulca mode mode [bot]` | Manage Server | Switches every linked channel of one bot, or of all (default), to a listening mode (`ambient`, `toggle`, `transcribe`, `wake`). Takes effect at once, no relink needed: changed channels restart their session and keep their memory. `/mulca link mode:…` on a linked channel applies the same way. |
| `/mulca unlink [channel]` | Manage Server | Stops MULCA serving a channel. Its memory is kept; linking it again brings it back. |
| `/mulca bot add` | Manage Server | Adds another bot account: its token goes in a private form, it starts at once, and the reply has its invite link. Needed for two voice groups talking at once in one server. |
| `/mulca bot remove bot [force]` | Manage Server | Stops an added bot and deletes its token. Refused while it still serves channels, unless `force` (which unlinks them). |
| `/mulca bot list` | Manage Server | Every bot of this deployment and what it's doing. Never shows tokens. |

`/mulca` is hidden from members without Manage Server. Only the main bot (the one
whose token is `DISCORD_BOT_TOKEN`) registers commands, and it controls the added bots
too, so it must be in every server where the commands are needed. `/mulca bot ...`
acts on the whole deployment, not just the server it's used in. If the commands don't
appear at all, the bot was invited without the `applications.commands`
scope: invite it again with scopes `bot` and `applications.commands`.

## Voice

Link a voice channel with a text channel and MULCA joins it whenever
someone is in it, and leaves when it empties. Text and voice share one
MUCA-Server session (`channel:<text channel id>`), so they share one memory:
what was said out loud is known in the text channel and vice versa.

- **Listening** (`voice/capture.py`, `voice/synchronizer.py`): each user's
  audio arrives separately (discord-ext-voice-recv); Discord's end-to-end
  voice encryption (DAVE) is undone with discord.py's own DAVE session. Every
  100 ms the user holding the floor (loudest, with a 400 ms hang time) is
  sent up as one `audio_stream` frame -- also when nobody speaks, so the
  server always knows the playback state. This is the Unity package's
  UserAudioSynchronizerBasic, ported.
- **Speaking** (`voice/player.py`): spoken replies (`state_update.audio`)
  play in real time; `isNotifying`/`playbackTimeMs` are reported back exactly
  as the Unity client's AssistantAudioPusher does, and what was played is
  echoed as `playback_frame` for the intervention agent. Talking over MULCA
  stops it (the server sends `clearAudioQueue`).
- **Transcripts**: a spoken reply is not posted to the text channel unless
  the link was made with `transcripts: True`.
- **Roster** (`BotRuntime.roster_voice`/`roster_text`, `runtime.py`): voice
  sends its own roster (the voice channel's actual members), separately
  from the text channel's -- these used to be one `roster()` returning the
  *union* of both, so a voice-only participation strategy was really being
  judged against the text channel's membership, not who was actually on
  the call. `update_participants()` re-sends voice's roster whenever
  someone joins/leaves the channel (`on_voice_state_update`) or takes the
  floor for the first time, not on a timer.
- **Watchdog** (`voice/bridge.py`): recovers from two real failure modes --
  OpenAI's 60-minute Realtime session limit, and the tick loop stalling or
  dying outright (both confirmed live). Tier 1, tried first, just reopens
  the MUCA-Server session (handles the 60-minute limit on its own) and
  checks that a tick succeeds; tier 2, reached whenever tier 1 doesn't
  verifiably fix things -- not treated as a rare last resort -- is a full
  Discord leave-and-rejoin of the voice channel. Three consecutive failed
  ticks (`WATCHDOG_FAILURE_THRESHOLD`) trigger it, not one -- a single
  blip isn't worth reacting to. Failures and recoveries are only ever
  logged server-side; nothing is announced in Discord.

No ffmpeg needed: audio goes in and out as raw PCM.

To try it on your own test server, follow
[`TRYING_ON_DISCORD.md`](TRYING_ON_DISCORD.md): setup, a preflight check
(`python -m mulca_discord.preflight --voice-test 10`), and a step-by-step
trial.

**Not verified against a live Discord voice channel yet** -- the pieces are
unit-tested with synthetic audio, and MUCA-Server's voice path was verified
live against OpenAI (`MUCA-Server/scripts/smoke_client.py`). The first live
run should confirm per-user receive works with DAVE on (the likeliest place
for trouble: `voice/capture.py`'s `_undo_dave`).

## Layout

```
mulca_discord/
  discord_client.py    Builds the Discord client: intents, and wiring it to
                       a BotRuntime
  runtime.py           BotRuntime (one bot: channel scoping, DM detection,
                       rosters, voice, pause/restart/status) and BotManager
  commands.py          The slash commands: /restart and /mulca
  sessions.py          One MUCA-Server session per scope ("channel:<id>" or
                       "dm:<user_id>"), opened lazily, reopened when lost
  muca_client.py       One WebSocket session against MUCA-Server for one scope:
                       the handshake, user_text, audio_stream, playback_frame;
                       assistant_text / state_update back
  dispatch.py          Turns assistant_text deltas into throttled Discord
                       messages (split at Discord's 2000-character limit)
  links.py             Which text + voice channels each bot serves, and the
                       SQLite store keeping them (with paused state)
  voice/               The voice channel: capture, floor, playback, bridge
  courses/             The course setups: a shared persona and task, and per
                       course (aui/, imi/) its material and project schedule,
                       sent as the main agent's instructions at every connect
  __main__.py          Entrypoint: `python -m mulca_discord`
```

Cognition (working memory, strategies, both LLMs, episodic log) lives in
`MUCA-Server/muca_server/cognition/` and `muca_server/agents/` now, not here.
MUCA-Server's main agent is generic: the teaching assistant, and each
course's material, live in `mulca_discord/courses/`. To update them, edit those
files and push MULCA; sessions pick them up as they reconnect.

Which course a Discord server gets: `/mulca course` (for every bot there, or
with `bot:` for one), else the course whose id the server's name contains as
a word ("IMI 2026/27" -> IMI), else AUI. `/mulca course` with no course shows
each bot's and why; `auto` goes back to the server's name. To add a course,
add a `courses/<id>/knowledge/` folder like `imi/`'s.
