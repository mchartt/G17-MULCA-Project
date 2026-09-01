# MULCA prototype (text bot)

Implements the architecture in `../BLUEPRINT.md`: orchestrator + shared working
memory + a stateful, persistent intervention agent + main LLM, running against
a Discord text channel. Audio is out of scope here — see **"Where audio plugs
in"** below for the exact seam a colleague's `AudioChannelAdapter` needs to
conform to.

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
  documented seam so far.
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

```bash
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

cp .env.example .env
# fill in DISCORD_BOT_TOKEN and OPENAI_API_KEY in .env
# MULCA_CHANNEL_IDS is optional -- comma-separated channel IDs to restrict to

python manage.py migrate
python manage.py run_discord_bot --autoreload
```

`--autoreload` restarts the bot automatically on code changes during active
dev/debugging (Django's autoreload utility, same mechanism `runserver` uses).
Omit it for a run where clean-shutdown persistence (§11.1) matters — on
Windows the autoreloader's child-subprocess model was found to swallow
Ctrl+C before the shutdown-save code runs (see the "Startup/shutdown
persistence" entry above).

The bot needs the "Message Content" privileged intent enabled in the Discord
developer portal (`discord_adapter.py` requests `intents.message_content = True`).

## Where audio plugs in

Two things an `AudioChannelAdapter` module needs to do — both are already
consumed by `core/orchestrator.py`, no orchestrator changes required to add it:

1. **Per-utterance events.** For each completed utterance, construct a
   `core.events.ConversationEvent(speaker_id=..., modality="audio",
   content=<text/semantic representation from the native multimodal audio
   model>, timestamp=..., channel_id=...)` and call
   `await orchestrator.enqueue(event)` — the exact same call
   `discord_adapter.py`'s `on_message` makes for text. `content` must come from
   the audio model's own understanding of the utterance, not a separate
   speech-to-text stage (BLUEPRINT.md "Technical constraints").
2. **Continuous activity signal (optional for a first pass).** For
   started/stopped-speaking events between utterances, construct a
   `core.events.SpeechActivityEvent` and push it through the same
   `orchestrator.enqueue()` path. The orchestrator currently no-ops on these
   (`core/orchestrator.py::_consume`, the `SpeechActivityEvent` branch) — hook
   in real trigger-variable updates there when needed, without touching the
   `ConversationEvent` path.

Both event types funnel into the **same per-scope `asyncio.Queue`** as text
events (`Orchestrator._queue_for`, keyed by `_scope_key` — see "Channel/instance
scoping" above), so audio and text events for the same scope are always
processed one at a time, in arrival order — this is what rules out races
between the two streams once both are live (see `core/orchestrator.py`'s
module docstring and BLUEPRINT.md §5/§6).

Dispatch (bot speaking back) is not yet defined for audio — `core/main_llm.py`
only yields text chunks. Wiring text-to-speech-out (or a native audio-output
model) is the colleague's side to design against this same `stream_reply()`
text-chunk generator; not designed here.

## Layout

```
mulca/
  core/            framework-agnostic: WM, orchestrator, both LLM wrappers, strategies, events
  bot/             Django app: episodic log model + Discord text adapter
  config/          personas / tasks / strategies YAML (BLUEPRINT.md §1, §4 "Skills")
    strategies/    one flat pool -- which subset is active is chosen independently
                   in run_discord_bot.py's ACTIVE_STRATEGY_IDS, not derived from
                   which task is loaded (persona/task/strategies are three
                   separate choices, per BLUEPRINT.md §9's reuse goal)

```
