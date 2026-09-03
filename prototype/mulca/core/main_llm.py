"""Main LLM (BLUEPRINT.md §1 / §8: procedural memory, not the decision locus).

Generates the actual utterance, streaming tokens (BLUEPRINT.md "Technical
constraints" -- OpenAI streaming models). Reads main.forced_context XOR
main.latest_strategy_id/prompt_fragment from its own WM namespace
(core.working_memory.WorkingMemory.main_view) -- never both, by construction.

Also runs the management cycle's summarization (BLUEPRINT.md §11) -- moved
here from the intervention agent after a live quality issue: that model is
meant to be lightweight/fast for judgment calls, not scoped for dense
synthesis, and it showed (summaries degraded to topic lists rather than
retaining specifics). Unlike the intervention agent's persistent session,
this is a stateless call -- WM's own (pre-truncation) history plus the
previous summary are the only source of truth, so this *revises* the
existing summary each cycle rather than regenerating fresh from an unbounded
session memory the main LLM doesn't have.
"""
import json

from openai import AsyncOpenAI

MAIN_MODEL = "gpt-4o"

_MANAGEMENT_SCHEMA = {
    "name": "management_summary",
    "schema": {
        "type": "object",
        "properties": {
            "history_summary": {"type": "string"},
            "participant_roles_summary": {"type": "string"},
        },
        "required": ["history_summary", "participant_roles_summary"],
        "additionalProperties": False,
    },
    "strict": True,
}


class MainLLM:
    def __init__(self, client: AsyncOpenAI, strategy_store):
        self._client = client
        self._strategies = strategy_store

    async def run_management_cycle(self, wm) -> dict:
        history_text = "\n".join(f"{e.label()}: {e.content}" for e in wm.history)
        response = await self._client.chat.completions.create(
            model=MAIN_MODEL,
            messages=[
                {"role": "system", "content": (
                    "You are producing an updated internal summary of an ongoing "
                    "conversation, for another LLM to read -- not a human. Optimize for "
                    "information density: concrete facts, names, numbers, and decisions, "
                    "not a list of topics that were merely mentioned. Target roughly "
                    "250-300 words for history_summary."
                )},
                {"role": "user", "content": (
                    f"Previous summary (empty if this is the first cycle):\n"
                    f"{wm.history_summary or '(none yet)'}\n\n"
                    f"Previous participant/roles summary:\n"
                    f"{wm.participant_roles_summary or '(none yet)'}\n\n"
                    f"New messages since then:\n{history_text}\n\n"
                    "Produce an updated history_summary that incorporates the new "
                    "messages into the previous summary (not just the new messages "
                    "alone -- earlier content that isn't repeated below must still be "
                    "retained), and an updated participant_roles_summary."
                )},
            ],
            response_format={"type": "json_schema", "json_schema": _MANAGEMENT_SCHEMA},
        )
        result = json.loads(response.choices[0].message.content)
        return {
            "history_summary": result["history_summary"],
            "participant_roles_summary": result["participant_roles_summary"],
        }

    async def run_dm_management_cycle(self, wm) -> str:
        """DM-specific, simpler version of run_management_cycle (BLUEPRINT.md
        §11.2): a DM has exactly one participant, so there's no
        participant_roles_summary to track -- just an updated history summary.
        Plain-text response, not JSON-schema-constrained, since there's only
        the one field to produce."""
        history_text = "\n".join(f"{e.label()}: {e.content}" for e in wm.history)
        response = await self._client.chat.completions.create(
            model=MAIN_MODEL,
            messages=[
                {"role": "system", "content": (
                    "You are producing an updated internal summary of an ongoing "
                    "private one-on-one conversation, for another LLM to read -- "
                    "not a human. Optimize for information density: concrete "
                    "facts, names, numbers, and decisions, not a list of topics "
                    "that were merely mentioned. Target roughly 150-200 words. "
                    "Respond with only the updated summary text, nothing else."
                )},
                {"role": "user", "content": (
                    f"Previous summary (empty if this is the first cycle):\n"
                    f"{wm.history_summary or '(none yet)'}\n\n"
                    f"New messages since then:\n{history_text}\n\n"
                    "Produce an updated summary that incorporates the new "
                    "messages into the previous summary -- earlier content that "
                    "isn't repeated below must still be retained."
                )},
            ],
        )
        return response.choices[0].message.content.strip()

    def _directive(self, view: dict) -> str:
        if view["forced_context"] is not None:
            return f"Forced intervention: {view['forced_context']}"
        if view["strategy_id"] is not None:
            strategy = self._strategies.get(view["strategy_id"])
            return strategy.prompt_template.format(prompt_fragment=view["prompt_fragment"])
        return ""

    async def stream_reply(self, wm):
        """Yields text chunks as they stream from the model."""
        view = wm.main_view()
        directive = self._directive(view)
        # Once a management cycle (BLUEPRINT.md §11) has run, view["history"]
        # is only the last few raw turns -- everything before that is in
        # history_summary instead. Both are rendered; on turn 1-8 the summary
        # is simply empty.
        history_text = "\n".join(f"{e.label()}: {e.content}" for e in view["history"][-20:])
        summary_block = ""
        if view["history_summary"] or view["participant_roles_summary"]:
            summary_block = (
                f"Summary of the conversation so far:\n{view['history_summary'] or '(none yet)'}\n\n"
                f"Participants and roles observed so far:\n{view['participant_roles_summary'] or '(none yet)'}\n\n"
            )
        # Retrieved EpisodicLog rows (BLUEPRINT.md §12's provide_summary) --
        # only present on the turn that strategy fires, cleared right after.
        retrieved_block = f"Retrieved conversation history:\n{view['retrieved_context']}\n\n" if view["retrieved_context"] else ""
        # Strategy-sourced directives come from the intervention agent -- a
        # lighter, faster model whose job is judgment (when/which strategy/why),
        # not crafting the response. Framed explicitly as guidance to interpret,
        # not a script to execute verbatim, so phrasing/tone/delivery stays this
        # (more capable) model's call. forced_context is different -- it's
        # deterministic orchestrator output (e.g. "you were addressed by X
        # saying Y"), not the intervention agent's judgment, so it doesn't need
        # the same framing.
        directive_label = (
            "High-level guidance from a lightweight judgment step -- this is the "
            "rationale and rough target (why this applies now, and who/what if "
            "relevant), not literal wording. Use your own judgment for exact "
            "phrasing, tone, and delivery:"
            if view["strategy_id"] is not None
            else "Current directive:"
        )
        system_prompt = (
            f"{view['persona']}\n\n"
            f"Task context:\n{view['task_knowledge']}\n\n"
            f"Available tools:\n{view['tools_description'] or 'none'}\n\n"
            f"{summary_block}"
            f"{retrieved_block}"
            f"{directive_label}\n{directive or 'Respond naturally as the ongoing conversation warrants.'}"
        )
        stream = await self._client.chat.completions.create(
            model=MAIN_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Recent conversation:\n{history_text}"},
            ],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
