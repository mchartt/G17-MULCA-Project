"""Fixed, config-defined strategy set (BLUEPRINT.md §1 / §4 "Skills").

Strategies are loaded once at boot from YAML and never mutated at runtime --
the intervention LLM *selects and parameterizes* from this set, it does not
compose new strategies (BLUEPRINT.md §1). This is the "explicit" half of
procedural memory; the foundation model's general competence is the implicit
half, and isn't modeled here.

All strategy files live in one flat pool (config/strategies/*.yaml) --
persona, task, and which strategies are active are three independent choices
made at startup (BLUEPRINT.md §9's reuse goal: assemble an instance by
selecting from a shared database, not by one config auto-deriving another).
`load_from_dir`'s optional `active_ids` is that selection -- which subset of
the pool this instance actually uses.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import yaml


@dataclass
class Strategy:
    id: str
    trigger_description: str
    trigger_variables: list
    prompt_template: str
    # Optional predefined numeric threshold, e.g. {"variable": "gini_index", "min": 0.3}.
    # Surfaced to the intervention agent as a concrete number to reason against
    # (catalog_for_prompt) -- the firing decision is still the LLM's judgment
    # call, this just replaces vague language ("high imbalance") with a fixed,
    # tunable number defined in config.
    trigger_threshold: Optional[dict] = None
    # Minimum number of (non-bot) messages that must pass after this strategy
    # actually fires before it's allowed to fire again (BLUEPRINT.md §10.5).
    # 0 = no cooldown. Enforced deterministically by the orchestrator
    # (WorkingMemory.strategy_in_cooldown), not left to the LLM to remember.
    cooldown_messages: int = 0


class StrategyStore:
    def __init__(self, strategies: Dict[str, Strategy]):
        self._strategies = strategies

    @classmethod
    def load_from_dir(cls, directory: str, active_ids: Optional[list] = None) -> "StrategyStore":
        """Loads the full strategy pool from `directory`. If `active_ids` is
        given, only that subset is kept -- the independent "which strategies
        are active" choice, made at startup alongside (not derived from)
        persona/task choices. An id in `active_ids` that doesn't exist in the
        pool is a config mistake worth failing loudly on, not silently
        ignoring."""
        strategies = {}
        for path in sorted(Path(directory).glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            strategy = Strategy(
                id=data["id"],
                trigger_description=data["trigger_description"],
                trigger_variables=data.get("trigger_variables", []),
                prompt_template=data["prompt_template"],
                trigger_threshold=data.get("trigger_threshold"),
                cooldown_messages=data.get("cooldown_messages", 0),
            )
            strategies[strategy.id] = strategy

        if active_ids is not None:
            missing = set(active_ids) - strategies.keys()
            if missing:
                raise ValueError(f"active_ids references unknown strategies: {sorted(missing)}")
            strategies = {sid: strategies[sid] for sid in active_ids}

        return cls(strategies)

    def get(self, strategy_id: str) -> Strategy:
        return self._strategies[strategy_id]

    def all(self):
        return list(self._strategies.values())

    def catalog_for_prompt(self) -> str:
        """Rendered for the intervention LLM's system prompt -- id, trigger
        description, and which variables it needs, so it can decide *whether*
        to fire without seeing the prompt_template itself (that's assembled
        after selection, from the strategy's own template)."""
        lines = []
        for strategy in self.all():
            threshold_line = ""
            if strategy.trigger_threshold:
                t = strategy.trigger_threshold
                threshold_line = f"\n  threshold: only fire if {t['variable']} >= {t['min']}"
            cooldown_line = (
                f"\n  cooldown: do not select again within {strategy.cooldown_messages} messages of firing"
                if strategy.cooldown_messages
                else ""
            )
            variables_line = (
                ", ".join(strategy.trigger_variables)
                if strategy.trigger_variables
                else "none -- judge this directly from the conversation content"
            )
            lines.append(
                f"- id: {strategy.id}\n"
                f"  trigger: {strategy.trigger_description}\n"
                f"  variables_used: {variables_line}"
                f"{threshold_line}"
                f"{cooldown_line}"
            )
        return "\n".join(lines)
