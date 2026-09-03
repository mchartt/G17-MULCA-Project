"""Shared working memory object (BLUEPRINT.md §3).

One WM instance per *scope* -- one shared instance for the group's registered
channels (text+voice), and a separate one per DM-ing user (BLUEPRINT.md's
"Channel/instance scoping" section) -- not one per raw Discord channel id.
A single shared object with namespaced sections, not two synced WM objects --
see BLUEPRINT.md §3 for the tradeoff and the field-ownership table this class
mirrors exactly.

Ownership, enforced here by which methods exist (not just by convention):
  - static.*            : written once at boot by config loaders, read-only after.
  - shared.*            : written only by the orchestrator.
  - main.forced_context : written only by the orchestrator (forced-intervention bypass).
  - main.latest_strategy_id / latest_prompt_fragment:
        authored by the intervention LLM's output; the orchestrator only relays
        it in verbatim (`set_intervention_result`), never edits its content.

main.forced_context and (latest_strategy_id/prompt_fragment) are mutually
exclusive per cycle by construction: the orchestrator calls exactly one of
set_forced_context / set_intervention_result per cycle, and clears the other,
so the main LLM's prompt-builder never has to reconcile both at once.
"""
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class WorkingMemory:
    scope_key: str  # "group", or "dm:<user_id>" -- see module docstring

    # --- static, boot-time, config-loader-owned ---
    intervention_persona: str = ""
    intervention_task_knowledge: str = ""
    main_persona: str = ""
    main_task_knowledge: str = ""
    main_tools_description: str = ""  # placeholder seam only (BLUEPRINT.md §3) -- not a real tool loop

    # --- per-turn, orchestrator-owned ---
    history: list = field(default_factory=list)          # list[ConversationEvent]
    trigger_variables: dict = field(default_factory=dict)  # e.g. {"gini_index": 0.42}

    # --- per-turn, intervention-LLM-output-owned (orchestrator relays only) ---
    latest_strategy_id: Optional[str] = None
    latest_prompt_fragment: Optional[str] = None

    # --- per-turn (rare), orchestrator-owned, mutually exclusive with the two above ---
    forced_context: Optional[str] = None

    # --- per-turn (rare), orchestrator-owned: retrieved EpisodicLog rows for
    # `provide_summary` (BLUEPRINT.md §12) -- set only on the turn that
    # strategy fires, cleared after like forced_context/strategy fields.
    retrieved_context: Optional[str] = None

    # --- orchestrator-owned bookkeeping (BLUEPRINT.md §10.5): {strategy_id: message_count
    # at the moment it last actually fired}. Not conversational content -- agent-state
    # bookkeeping, kept here anyway per §10.5's "practically, fine to put in WM".
    recent_actions: dict = field(default_factory=dict)

    # --- management cycle (BLUEPRINT.md §11), group scope only ---
    total_message_count: int = 0  # monotonic, survives history truncation below -- what "every 8th message" counts against
    history_summary: str = ""              # dense, LLM-facing (§11) -- not the user-facing summary (§12)
    participant_roles_summary: str = ""    # the fuller "team role" concept (§4/§7.6), beyond the presence roster

    def append_history(self, event) -> None:
        self.history.append(event)

    def increment_message_count(self) -> int:
        self.total_message_count += 1
        return self.total_message_count

    def apply_management_cycle(self, history_summary: str, participant_roles_summary: str) -> None:
        """Replaces (not appends to) the raw history with a condensed summary
        + a short raw tail (BLUEPRINT.md §11's resolution of §7.2b's
        WM-history-growth question) -- keeps the window fixed-size rather
        than growing unboundedly with session length."""
        self.history_summary = history_summary
        self.participant_roles_summary = participant_roles_summary
        self.history = self.history[-5:]

    def record_action(self, strategy_id: str, message_count: int) -> None:
        self.recent_actions[strategy_id] = message_count

    def strategy_in_cooldown(self, strategy) -> bool:
        """Hard, deterministic check (BLUEPRINT.md §10.5) -- not something left
        to the intervention agent to remember and self-restrain from.

        Uses total_message_count, NOT trigger_variables["message_count"] --
        the latter is len(history) at compute time, which the management
        cycle (§11) truncates every 8th message. Comparing against it meant
        the "how long since this fired" gap could reset or even go negative
        across a truncation, leaving a strategy stuck thinking it was still
        in cooldown far longer than cooldown_messages actually specifies (a
        real bug, found from a live report: participation_equality fired once
        and then never again). total_message_count is monotonic and survives
        truncation, same reason it's what the management-cycle-every-8 check
        already used.
        """
        if not strategy.cooldown_messages:
            return False
        last_fired = self.recent_actions.get(strategy.id)
        if last_fired is None:
            return False
        return (self.total_message_count - last_fired) < strategy.cooldown_messages

    def set_trigger_variables(self, variables: dict) -> None:
        self.trigger_variables = variables

    def set_intervention_result(self, strategy_id: Optional[str], prompt_fragment: Optional[str]) -> None:
        """Relay-only: the *content* of these two fields is authored by the intervention LLM."""
        self.latest_strategy_id = strategy_id
        self.latest_prompt_fragment = prompt_fragment
        self.forced_context = None

    def set_forced_context(self, context: str) -> None:
        self.forced_context = context
        self.latest_strategy_id = None
        self.latest_prompt_fragment = None

    def set_retrieved_context(self, text: Optional[str]) -> None:
        self.retrieved_context = text

    def clear_turn_output(self) -> None:
        """Called after the main LLM has consumed this cycle's directive, so a
        turn where nothing new fires doesn't accidentally replay stale strategy
        output on the next cycle."""
        self.latest_strategy_id = None
        self.latest_prompt_fragment = None
        self.forced_context = None
        self.retrieved_context = None

    # --- read-side helpers, namespaced per role (BLUEPRINT.md §3 "role-scoped access") ---

    def intervention_view(self) -> dict:
        """Unused since the intervention agent became stateful (BLUEPRINT.md
        §10.1) -- kept for reference, not dead-code cleanup yet. persona/task
        are now sent once, as constructor args, at RealtimeInterventionLLM.connect()
        time (never re-read from WM per turn, since the session remembers them
        itself); history/trigger_variables are read directly off wm's raw
        attributes in decide(), not through this method, since what's needed
        each turn is only the *new* increment + current dynamic state, not a
        full reconstructed context the way the stateless main LLM needs via
        main_view(). See BLUEPRINT.md §10.1 for the full reasoning."""
        return {
            "persona": self.intervention_persona,
            "task_knowledge": self.intervention_task_knowledge,
            "history": list(self.history),
            "trigger_variables": dict(self.trigger_variables),
        }

    def main_view(self) -> dict:
        return {
            "persona": self.main_persona,
            "task_knowledge": self.main_task_knowledge,
            "tools_description": self.main_tools_description,
            "history": list(self.history),
            "history_summary": self.history_summary,
            "participant_roles_summary": self.participant_roles_summary,
            "strategy_id": self.latest_strategy_id,
            "prompt_fragment": self.latest_prompt_fragment,
            "forced_context": self.forced_context,
            "retrieved_context": self.retrieved_context,
        }
