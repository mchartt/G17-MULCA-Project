"""Orchestrator (BLUEPRINT.md §2 / §5, scoping per the "Channel/instance
scoping" section).

Deterministic, non-LLM glue. Concurrency model: one asyncio.Queue and one
consumer task **per scope**, not per raw Discord channel. A scope is either
`"group"` (the one text channel + one voice channel this instance is
registered to -- they share a single WM/session/queue, since they're one
conversation) or `"dm:<user_id>"` (a private, per-user context, kept apart
from the group and never persisted to the episodic log). See `_scope_key`.

Both the text adapter today and a future AudioChannelAdapter call the same
`enqueue()`; events for a given scope land on the same queue and the single
consumer processes them strictly one at a time -- there is no window where
two events in the same scope are handled concurrently, by construction of
this queue+single-consumer structure, not by convention. A new message
arriving mid-generation is queued, not interleaved (BLUEPRINT.md §5).
`event.channel_id` is never used as a state key -- only as dispatch-routing
metadata (which physical channel/DM a reply goes back to).
"""
import asyncio
import time
import traceback
from dataclasses import asdict

from .events import ConversationEvent, SpeechActivityEvent
from .forced_intervention import check_forced_intervention
from .trigger_variables import compute_trigger_variables
from .working_memory import WorkingMemory

# BLUEPRINT.md §12: "fairly high N" for provide_summary's retrieval window --
# recency-based, not relevance-ranked (deliberately not a real RAG pipeline).
SUMMARY_RETRIEVAL_LIMIT = 50

# BLUEPRINT.md §11.2: DM memory cycle cadence -- a separate, independently
# tunable constant from the group's every-8 (they happen to share the same
# value today, but there's no reason they must; a DM's pace may warrant a
# different cadence, not yet decided).
DM_MANAGEMENT_CYCLE_INTERVAL = 8


class Orchestrator:
    def __init__(self, strategy_store, intervention_llm_factory, main_llm, bot_user_id, dispatch_fn, log_fn, persona_config, task_config, roster_fn=None, bot_display_name="MULCA", retrieve_log_fn=None, persistence_channel_id=None, snapshot_load_fn=None, snapshot_save_fn=None):
        self._strategies = strategy_store
        self._bot_display_name = bot_display_name
        # BLUEPRINT.md §10.1: the intervention agent is a persistent, stateful
        # session with its own memory -- one per scope, not one shared
        # instance, so the group's conversation and any individual's DM don't
        # bleed into each other. `intervention_llm_factory(scope_key) -> agent`
        # builds one; connect() is called lazily on first use.
        self._intervention_llm_factory = intervention_llm_factory
        self._main_llm = main_llm
        self._bot_user_id = bot_user_id
        self._dispatch_fn = dispatch_fn  # async (channel_id, async_text_chunk_iterator) -> None
        self._log_fn = log_fn            # async (dict) -> None
        self._persona_config = persona_config
        self._task_config = task_config
        # async (channel_id) -> {user_id: display_name}; only called for the
        # "group" scope -- a roster (who's present in a shared channel) has no
        # meaning for a 1:1 DM. None means "no roster available" (e.g. audio
        # adapter doesn't have one yet).
        self._roster_fn = roster_fn
        # async (channel_id, limit) -> list[dict]; BLUEPRINT.md §12's
        # provide_summary retrieval. None means the strategy silently
        # produces nothing to retrieve (e.g. not wired up yet).
        self._retrieve_log_fn = retrieve_log_fn
        # BLUEPRINT.md §11.1: startup/shutdown persistence, "group" scope
        # only -- keyed by the instance's primary registered channel id
        # (resolved once at boot, see run_discord_bot.py). If
        # persistence_channel_id is None (MULCA_CHANNEL_IDS unset -- no
        # single stable identity to key by), persistence is silently
        # disabled rather than guessing at a key.
        self._persistence_channel_id = persistence_channel_id
        self._snapshot_load_fn = snapshot_load_fn    # async (channel_id) -> dict | None
        self._snapshot_save_fn = snapshot_save_fn    # async (channel_id, dict) -> None

        self._queues: dict[str, asyncio.Queue] = {}
        self._wms: dict[str, WorkingMemory] = {}
        self._consumer_tasks: dict[str, asyncio.Task] = {}
        self._intervention_agents: dict[str, object] = {}

    def _scope_key(self, event) -> str:
        """"group" for the instance's registered channels (text+voice, shared
        WM/session), "dm:<user_id>" for a private DM (own WM/session, never
        persisted -- see the episodic-log skip in _handle_conversation_event).
        """
        if getattr(event, "is_dm", False):
            return f"dm:{event.speaker_id}"
        return "group"

    def _wm_for(self, scope_key: str) -> WorkingMemory:
        if scope_key not in self._wms:
            wm = WorkingMemory(scope_key=scope_key)
            wm.intervention_persona = self._persona_config["intervention"]
            wm.intervention_task_knowledge = self._task_config["description"]
            wm.main_persona = self._persona_config["main"]
            wm.main_task_knowledge = self._task_config["description"]
            wm.main_tools_description = ""  # placeholder seam only, BLUEPRINT.md §3
            self._wms[scope_key] = wm
        return self._wms[scope_key]

    async def load_group_snapshot(self) -> None:
        """BLUEPRINT.md §11.1 startup half. Call once, before the first
        message arrives -- if "group" WM already exists (shouldn't normally
        happen this early), does nothing rather than clobbering it."""
        if not self._persistence_channel_id or not self._snapshot_load_fn or "group" in self._wms:
            return
        snapshot = await self._snapshot_load_fn(self._persistence_channel_id)
        wm = self._wm_for("group")
        if snapshot is None:
            print(f"[MULCA debug] no WM snapshot found for channel {self._persistence_channel_id}, starting fresh")  # TODO: remove once live-tested
            return
        wm.history_summary = snapshot["history_summary"]
        wm.participant_roles_summary = snapshot["participant_roles_summary"]
        wm.total_message_count = snapshot["total_message_count"]
        wm.history = [ConversationEvent(**item) for item in snapshot["history_tail"]]
        print(f"[MULCA debug] loaded WM snapshot for channel {self._persistence_channel_id}: total_message_count={wm.total_message_count}, history_tail={len(wm.history)}")  # TODO: remove once live-tested

    async def save_group_snapshot(self) -> None:
        """BLUEPRINT.md §11.1 shutdown half. Called by run_discord_bot.py
        after client.run() returns on a clean shutdown -- does nothing if the
        "group" scope was never used this run, or persistence isn't
        configured. NOT called on an unclean exit (crash, kill -9) -- see
        BLUEPRINT.md §11.1's open question about that gap."""
        if not self._persistence_channel_id or not self._snapshot_save_fn:
            return
        wm = self._wms.get("group")
        if wm is None:
            return
        snapshot = {
            "history_summary": wm.history_summary,
            "participant_roles_summary": wm.participant_roles_summary,
            "history_tail": [asdict(event) for event in wm.history],
            "total_message_count": wm.total_message_count,
        }
        await self._snapshot_save_fn(self._persistence_channel_id, snapshot)
        print(f"[MULCA debug] saved WM snapshot for channel {self._persistence_channel_id}: total_message_count={wm.total_message_count}")  # TODO: remove once live-tested

    async def _intervention_agent_for(self, scope_key: str):
        if scope_key not in self._intervention_agents:
            # wm may already carry a restored summary (BLUEPRINT.md §11.1) if
            # load_group_snapshot() ran before this agent was ever created --
            # true for "group" scope, since that happens at boot before any
            # message can arrive. Passed through so the session isn't blind
            # to it (§11.1's "known gap," now fixed).
            wm = self._wm_for(scope_key)
            agent = self._intervention_llm_factory(scope_key, wm.history_summary, wm.participant_roles_summary)
            await agent.connect()
            self._intervention_agents[scope_key] = agent
        return self._intervention_agents[scope_key]

    def _queue_for(self, scope_key: str) -> asyncio.Queue:
        if scope_key not in self._queues:
            queue: asyncio.Queue = asyncio.Queue()
            self._queues[scope_key] = queue
            self._consumer_tasks[scope_key] = asyncio.create_task(self._consume(scope_key, queue))
        return self._queues[scope_key]

    async def enqueue(self, event) -> None:
        """Single entry point for every channel adapter, text or audio."""
        await self._queue_for(self._scope_key(event)).put(event)

    async def _consume(self, scope_key: str, queue: asyncio.Queue) -> None:
        # An uncaught exception here used to kill this task silently -- every
        # later message for this scope would then sit in the queue forever,
        # with no error printed anywhere. Catching and logging here instead
        # keeps the consumer alive so one bad cycle doesn't take the whole
        # scope down. TODO: remove the print-based logging once past active
        # debugging in favor of something structured.
        while True:
            event = await queue.get()
            try:
                if isinstance(event, ConversationEvent):
                    await self._handle_conversation_event(scope_key, event)
                elif isinstance(event, SpeechActivityEvent):
                    # Continuous audio lane (BLUEPRINT.md §6): updates live state only,
                    # never itself triggers an LLM call. Not exercised by the text-only
                    # prototype; the seam exists so AudioChannelAdapter has somewhere to
                    # push without needing orchestrator changes.
                    pass
            except Exception:
                print(f"[MULCA ERROR] {scope_key}: unhandled exception while processing event, continuing")
                traceback.print_exc()
            finally:
                queue.task_done()

    async def _handle_conversation_event(self, scope_key: str, event: ConversationEvent) -> None:
        print(f"[MULCA debug] {scope_key} received: {event.speaker_id}: {event.content!r}")  # TODO: remove once live-tested
        wm = self._wm_for(scope_key)

        # Step 2: append to shared history.
        wm.append_history(event)
        message_count_for_cycle = wm.increment_message_count()

        # Step 3: recompute trigger variables (plain code, no LLM call).
        # Roster lookup recognizes participants who are present but haven't
        # spoken yet -- without it, someone completely silent is invisible to
        # gini_index/participant counts until their first message, which
        # understates imbalance while the group is still small. Meaningless
        # for a DM (it's always exactly one person), so skipped there.
        roster = {}
        if scope_key == "group" and self._roster_fn:
            roster = await self._roster_fn(event.channel_id)
        wm.set_trigger_variables(compute_trigger_variables(wm.history, self._bot_user_id, roster))
        print(f"[MULCA debug] {scope_key} roster={roster} trigger_variables={wm.trigger_variables}")  # TODO: remove once live-tested

        path = "none"
        strategy_id = None
        prompt_fragment = None
        needs_history = False
        needs_web_search = False

        # Step 4: forced-intervention check short-circuits step 5 (currently
        # defines only @mainllm -- see forced_intervention.py; real @mention
        # was removed from here, see its docstring for why).
        forced = check_forced_intervention(event, self._bot_user_id)
        if forced is not None:
            wm.set_forced_context(forced)
            path = "forced"
        else:
            # Step 5: intervention LLM decides (BLUEPRINT.md §10.1: a persistent,
            # per-scope session now, not a fresh stateless call).
            print(f"[MULCA debug] {scope_key} connecting/reusing intervention agent...")  # TODO: remove once live-tested
            intervention_agent = await self._intervention_agent_for(scope_key)
            print(f"[MULCA debug] {scope_key} asking intervention agent to decide...")  # TODO: remove once live-tested
            strategy_id, prompt_fragment, needs_history, needs_web_search = await intervention_agent.decide(wm)
            print(f"[MULCA debug] {scope_key} decision: strategy_id={strategy_id!r} prompt_fragment={prompt_fragment!r} needs_history={needs_history} needs_web_search={needs_web_search}")  # TODO: remove once live-tested

            # Hard cooldown veto (BLUEPRINT.md §10.5) -- enforced here,
            # deterministically, regardless of what the LLM picked. Not a
            # request the LLM might ignore; this is the actual guarantee.
            if strategy_id is not None and wm.strategy_in_cooldown(self._strategies.get(strategy_id)):
                print(f"[MULCA debug] {scope_key} vetoed {strategy_id!r}: still in cooldown")  # TODO: remove once live-tested
                strategy_id, prompt_fragment, needs_history = None, None, False

            if strategy_id is not None:
                wm.set_intervention_result(strategy_id, prompt_fragment)
                # total_message_count, not trigger_variables["message_count"] --
                # see WorkingMemory.strategy_in_cooldown's docstring for why
                # the latter breaks across a management-cycle truncation.
                wm.record_action(strategy_id, wm.total_message_count)
                path = "strategy"
            else:
                wm.set_intervention_result(None, None)

        main_output = ""
        if path in ("forced", "strategy"):
            # Retrieval need is orthogonal to which strategy fired (BLUEPRINT.md
            # §12): the intervention agent can set needs_history on any
            # strategy (in practice, mostly respond_when_addressed), and
            # provide_summary always needs it regardless of what the model
            # reported -- forced deterministically here rather than trusted to
            # the model, same spirit as the cooldown veto. Silently produces
            # nothing for DM scope (self._retrieve_log_fn is still called, but
            # DMs have no logged rows to find, by design -- see §12's DM note).
            # needs_web_search isn't acted on -- no web search capability
            # exists yet; only logged for visibility (step 7 below).
            if (needs_history or strategy_id == "provide_summary") and self._retrieve_log_fn:
                rows = await self._retrieve_log_fn(event.channel_id, SUMMARY_RETRIEVAL_LIMIT)
                retrieved_text = "\n".join(
                    f"{r['speaker']}: {r['content']}" + (f"\nMULCA: {r['main_llm_output']}" if r["main_llm_output"] else "")
                    for r in rows
                    if r["content"]
                )
                wm.set_retrieved_context(retrieved_text or "(no prior conversation found)")
                print(f"[MULCA debug] {scope_key} provide_summary retrieved {len(rows)} rows")  # TODO: remove once live-tested

            # Step 6: main LLM generates and streams; dispatch_fn forwards chunks
            # as they arrive rather than buffering the full completion
            # (BLUEPRINT.md "Technical constraints" -- streaming models).
            # Dispatch always targets the real Discord channel/DM the
            # triggering event came from (event.channel_id) -- routing is
            # per-event metadata, never the scope key used for state above.
            chunks = []

            async def collecting_stream():
                async for chunk in self._main_llm.stream_reply(wm):
                    chunks.append(chunk)
                    yield chunk

            await self._dispatch_fn(event.channel_id, collecting_stream())
            main_output = "".join(chunks)
            if main_output:
                # The bot's own reply is part of "what's happened" too -- without
                # this, neither the intervention agent nor a later main LLM call
                # would know the bot already said something.
                wm.append_history(ConversationEvent(
                    speaker_id=self._bot_user_id,
                    modality=event.modality,
                    content=main_output,
                    timestamp=time.time(),
                    channel_id=event.channel_id,
                    speaker_display_name=self._bot_display_name,
                ))

        # Step 7: episodic log, regardless of outcome -- except for a DM,
        # which must never be written to persisted storage (BLUEPRINT.md's
        # "Channel/instance scoping" section: DM content is private to the
        # individual user, and EpisodicLog has no access-control concept).
        if scope_key != "group":
            # DM memory cycle (BLUEPRINT.md §11.2): simpler than the group's
            # (no participant_roles_summary -- a DM has exactly one
            # participant) and, critically, never logged anywhere -- a DM's
            # summary lives only in that DM's own in-memory WM, same privacy
            # boundary as everything else in this scope.
            if message_count_for_cycle % DM_MANAGEMENT_CYCLE_INTERVAL == 0:
                print(f"[MULCA debug] {scope_key} running DM management cycle at message #{message_count_for_cycle}")  # TODO: remove once live-tested
                history_summary = await self._main_llm.run_dm_management_cycle(wm)
                wm.apply_management_cycle(history_summary, wm.participant_roles_summary)
                intervention_agent = await self._intervention_agent_for(scope_key)
                intervention_agent.on_history_truncated(wm)
                print(f"[MULCA debug] {scope_key} DM management cycle result: {history_summary!r}")  # TODO: remove once live-tested
            wm.clear_turn_output()
            return

        await self._log_fn({
            "timestamp": time.time(),
            "channel_id": event.channel_id,
            "incoming_event_speaker": event.speaker_id,
            "incoming_event_content": event.content,
            "trigger_variables_snapshot": dict(wm.trigger_variables),
            "intervention_path": path,
            "strategy_id": strategy_id,
            "prompt_fragment": prompt_fragment,
            "main_llm_output": main_output or None,
        })

        wm.clear_turn_output()

        # Management cycle (BLUEPRINT.md §11): every 8th message, group scope
        # only (checked above -- this line is only reached for "group").
        # Runs after the regular turn, in the same event-processing cycle --
        # no new event type, just a plain check here, which gives the
        # identical serialization guarantee with less plumbing.
        if message_count_for_cycle % 8 == 0:
            print(f"[MULCA debug] {scope_key} running management cycle at message #{message_count_for_cycle}")  # TODO: remove once live-tested
            # Summarization itself is the main LLM's job (BLUEPRINT.md §11 --
            # moved off the intervention agent after a live quality issue).
            result = await self._main_llm.run_management_cycle(wm)
            wm.apply_management_cycle(result["history_summary"], result["participant_roles_summary"])
            # The intervention agent still needs to know wm.history shrank,
            # even though it no longer produces the summary -- its own
            # _sent_history_count bookkeeping (for decide()) would otherwise
            # desync (BLUEPRINT.md §11's "subtlety the implementation had to
            # handle").
            intervention_agent = await self._intervention_agent_for(scope_key)
            intervention_agent.on_history_truncated(wm)
            print(f"[MULCA debug] {scope_key} management cycle result: {result}")  # TODO: remove once live-tested

            await self._log_fn({
                "timestamp": time.time(),
                "channel_id": event.channel_id,
                "incoming_event_speaker": "",
                "incoming_event_content": "",
                "trigger_variables_snapshot": dict(wm.trigger_variables),
                "intervention_path": "management_cycle",
                "strategy_id": None,
                # Reusing these two free-text fields to hold the cycle's
                # output, rather than a schema change -- not designed in
                # detail per BLUEPRINT.md §11, this is the simplest fit.
                "prompt_fragment": result["participant_roles_summary"],
                "main_llm_output": result["history_summary"],
            })
