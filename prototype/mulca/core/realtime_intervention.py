"""Stateful, realtime-connected intervention agent (BLUEPRINT.md §10.1).

First version of the pattern described in §10.1: text events only, no audio
relay yet -- that's deliberate sequencing (§10's intro), not an oversight.
`decide(wm)` returns (strategy_id, prompt_fragment, needs_history,
needs_web_search) -- extended from the original 2-tuple once retrieval-need
became a judgment call orthogonal to which strategy fires (BLUEPRINT.md §12).

One instance per channel, created and connected lazily by
core.orchestrator.Orchestrator._intervention_agent_for -- a Realtime session
holds its own conversational state, so sharing one instance across channels
would conflate unrelated conversations (BLUEPRINT.md §10.1's ownership split:
the session is the intervention agent's own memory, WM stays authoritative for
what the main LLM gets and what's persisted).

Uses the GA (non-beta) Realtime API -- `client.realtime.connect(...)`, not
`client.beta.realtime.connect(...)`. The Beta shape was deprecated by OpenAI on
2026-05-12 and now hard-rejects connections with a
`beta_api_shape_disabled` error; this was caught via a live test, not
anticipated in advance -- see prototype/README.md's verification log.
"""
import json

TOOL_NAME = "signal_intervention"
REALTIME_MODEL = "gpt-realtime"


class RealtimeInterventionLLM:
    def __init__(self, client, strategy_store, persona: str, task_knowledge: str, is_dm: bool = False, model: str = REALTIME_MODEL, restored_history_summary: str = "", restored_participant_roles_summary: str = ""):
        self._client = client
        self._strategies = strategy_store
        self._persona = persona
        self._task_knowledge = task_knowledge
        self._is_dm = is_dm
        self._model = model
        # BLUEPRINT.md §11.1's known gap, fixed: if the WM was restored from a
        # snapshot before this agent was ever created (true for "group" scope,
        # since load_group_snapshot() runs at boot before any message can
        # arrive), the session's own memory would otherwise start blind to
        # everything except the restored 5-message raw tail. Given once, here,
        # not per-turn -- this is what the agent "already knew" walking in.
        self._restored_history_summary = restored_history_summary
        self._restored_participant_roles_summary = restored_participant_roles_summary
        self._connection_cm = None
        self._connection = None
        self._sent_history_count = 0  # how many WM history items already pushed to this session

    async def connect(self) -> None:
        """Opens the persistent session and configures it once. Persona, task
        knowledge, and the strategy catalog are sent here, at connect time --
        unlike the stateless version, they are never resent on every decide()
        call, because the session remembers them itself."""
        self._connection_cm = self._client.realtime.connect(model=self._model)
        self._connection = await self._connection_cm.__aenter__()
        strategy_ids = [s.id for s in self._strategies.all()]
        restored_note = (
            f"\n\nBefore this session began, here is what's already known about "
            f"this conversation (from before a restart): {self._restored_history_summary}\n"
            f"Participants/roles known so far: {self._restored_participant_roles_summary}"
            if self._restored_history_summary or self._restored_participant_roles_summary
            else ""
        )
        audience_note = (
            "You are in a private, one-on-one Discord DM with a single user -- "
            "there is no other audience, so unlike a group channel, there's no "
            "ambiguity about who a message is for. This does not mean every "
            "message needs a reply: still judge whether a response is actually "
            "warranted right now (e.g. a mid-thought fragment or a pure reaction "
            "may not need one), the same way you would in a group -- the only "
            "difference is there's no uncertainty about the intended audience."
            if self._is_dm else
            "You are watching an ongoing multi-user conversation, one message at "
            "a time, as it happens."
        )
        await self._connection.session.update(session={
            "type": "realtime",  # required in the GA session schema, wasn't in beta
            "output_modalities": ["text"],  # renamed from "modalities" in GA
            "instructions": (
                f"{self._persona}\n\n"
                f"Task context:\n{self._task_knowledge}\n"
                f"{restored_note}\n\n"
                f"{audience_note} For each new message, decide whether a "
                "conversational strategy should fire right now. If yes, call the "
                f"`{TOOL_NAME}` tool with the selected strategy id and a short "
                "parameterized instruction for the main response generator, plus two "
                "independent flags: needs_history true if answering well requires "
                "looking up something from earlier in the conversation that isn't "
                "already visible to you (e.g. a specific detail, or a request for a "
                "full recap); needs_web_search true if answering requires current "
                "information from outside this conversation entirely (not "
                "supported yet, but flag it so it's visible how often this comes "
                "up). Both default to false. An explicit @-mention of you always "
                "counts as being addressed. If no strategy should fire -- which is "
                "most of the time in a group, though not necessarily in a DM -- "
                "produce no output and do not call the tool. Never produce a "
                "conversational reply yourself; your only job is this judgment "
                "call.\n\n"
                "Available strategies:\n"
                f"{self._strategies.catalog_for_prompt()}"
            ),
            "tools": [
                {
                    "type": "function",
                    "name": TOOL_NAME,
                    "description": "Signal that a conversational strategy should fire now.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "strategy_id": {"type": "string", "enum": strategy_ids},
                            "prompt_fragment": {"type": "string"},
                            "needs_history": {"type": "boolean"},
                            "needs_web_search": {"type": "boolean"},
                        },
                        "required": ["strategy_id", "prompt_fragment", "needs_history", "needs_web_search"],
                    },
                },
            ],
            "tool_choice": "auto",
        })

    async def close(self) -> None:
        if self._connection_cm is not None:
            await self._connection_cm.__aexit__(None, None, None)
            self._connection = None
            self._connection_cm = None

    async def _push_new_history(self, wm) -> None:
        """Pushes only the WM history items this session hasn't already seen
        -- shared by decide() and run_management_cycle() since both need it.
        Note: this counts against wm.history's *current* contents, which a
        management cycle truncates (WorkingMemory.apply_management_cycle) --
        see on_history_truncated() for why that's safe."""
        new_events = wm.history[self._sent_history_count:]
        for event in new_events:
            await self._connection.conversation.item.create(item={
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": f"{event.label()}: {event.content}"}],
            })
        self._sent_history_count = len(wm.history)

    def on_history_truncated(self, wm) -> None:
        """Must be called by the orchestrator immediately after
        WorkingMemory.apply_management_cycle() truncates wm.history.
        _sent_history_count is an absolute index into wm.history; truncating
        the list out from under it would make _push_new_history's slice
        wrong (it'd think far fewer items were sent than actually were). The
        events remaining after truncation were already sent before the
        truncation happened, so the session already knows about them -- this
        just re-points the counter at the new (shorter) list."""
        self._sent_history_count = len(wm.history)

    async def decide(self, wm):
        """Returns (strategy_id, prompt_fragment, needs_history, needs_web_search).
        All None/False if no strategy fires. The two retrieval flags are
        independent of each other and of which strategy fired (BLUEPRINT.md
        §12) -- e.g. respond_when_addressed can fire with either, neither, or
        both. needs_web_search isn't acted on yet (no web search capability
        exists) -- captured for visibility only."""
        await self._push_new_history(wm)

        # Soft hint only -- the actual guarantee is the hard veto in
        # core.orchestrator (BLUEPRINT.md §10.5). This just avoids the model
        # wastefully re-selecting something it can already see is blocked.
        cooling_down = [s.id for s in self._strategies.all() if wm.strategy_in_cooldown(s)]
        cooldown_note = f"\nCurrently in cooldown, do not select: {cooling_down}" if cooling_down else ""

        await self._connection.conversation.item.create(item={
            "type": "message",
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": f"Current trigger variables: {json.dumps(wm.trigger_variables)}{cooldown_note}",
            }],
        })

        await self._connection.response.create()

        strategy_id = None
        prompt_fragment = None
        needs_history = False
        needs_web_search = False
        async for event in self._connection:
            if event.type == "response.function_call_arguments.done" and event.name == TOOL_NAME:
                args = json.loads(event.arguments)
                strategy_id = args.get("strategy_id")
                prompt_fragment = args.get("prompt_fragment")
                needs_history = bool(args.get("needs_history", False))
                needs_web_search = bool(args.get("needs_web_search", False))
            elif event.type == "response.done":
                break

        return strategy_id, prompt_fragment, needs_history, needs_web_search
