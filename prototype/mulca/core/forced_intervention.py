"""Forced-intervention bypass (BLUEPRINT.md §1 / §2).

Plain code, no LLM call -- skips the intervention LLM's judgment entirely.
Kept as an escape hatch for genuinely judgment-free rules, per BLUEPRINT.md
§7.7's "narrow, explicit list, not heuristics."

Real @mention was removed from here (see git history) once the intervention
agent also needed to judge *whether answering requires retrieval*
(BLUEPRINT.md §12): a bypass that skips the intervention agent entirely also
skips that judgment, which made an @mentioned question needing chat-log
context get a worse answer than the identical question asked without the
@mention. "Was I addressed" no longer needs resolving outside the
intervention agent for text -- the latency cost of always asking it turned
out not to matter in practice.

`@mainllm` is a separate, deliberate literal-text testing/debug rule: an
explicit, guaranteed way to force a direct main-LLM response without
depending on intervention-agent judgment at all -- useful for verifying the
main LLM/dispatch path works independent of judgment quality.
"""
from __future__ import annotations


def check_forced_intervention(event, bot_user_id: str) -> str | None:
    """Returns a forced-context string if a rule matches, else None."""
    if event.modality == "text" and "@mainllm" in event.content.lower():
        return (
            f"You were directly addressed by {event.label()}: \"{event.content}\". "
            "Respond to them directly."
        )
    return None
