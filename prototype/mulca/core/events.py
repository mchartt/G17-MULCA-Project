"""Event shapes crossing the channel-adapter -> orchestrator seam (BLUEPRINT.md §6).

Both TextChannelAdapter (this prototype) and a future AudioChannelAdapter push
ConversationEvent / SpeechActivityEvent onto the *same* per-channel queue the
orchestrator consumes (see core.orchestrator.Orchestrator._queue_for). That
single shared queue per channel is what prevents race conditions once audio and
text are both live: the orchestrator's consumer loop dequeues and fully
processes one event at a time, so audio and text events are serialized in
arrival order rather than handled concurrently. Nothing about this module
assumes text-only; it's the actual seam, not a placeholder for one.
"""
from dataclasses import dataclass
from typing import Any, Literal, Optional


@dataclass
class ConversationEvent:
    """One discrete conversational turn, regardless of modality.

    `content` is always a text representation an LLM can read: for text, the
    raw message; for audio (colleague's adapter), whatever text/semantic
    representation the native multimodal audio model produces for that
    utterance -- never a separate STT transcript (see BLUEPRINT.md "Technical
    constraints").
    """

    speaker_id: str
    modality: Literal["text", "audio"]
    content: str
    timestamp: float
    channel_id: str
    raw_ref: Optional[Any] = None  # modality-specific payload; orchestrator never inspects this
    # Human-readable label (e.g. Discord display name) for anything shown to an
    # LLM or dispatched back to the channel -- speaker_id stays the stable
    # identity used for counting/matching (e.g. forced_intervention's @mention
    # check, participant counting), never used for user-facing text.
    speaker_display_name: Optional[str] = None
    # True for a DM to the bot. Determines which WM this event is routed to
    # (a private, per-user scope, not the group's shared one) and that it is
    # never written to the persisted episodic log -- see
    # core.orchestrator.Orchestrator._scope_key and BLUEPRINT.md's
    # "Channel/instance scoping" section for why this is a privacy
    # requirement, not just a routing detail.
    is_dm: bool = False

    def label(self) -> str:
        return self.speaker_display_name or self.speaker_id


@dataclass
class SpeechActivityEvent:
    """High-frequency audio-only signal (BLUEPRINT.md §6, "Continuous event channel").

    Updates trigger variables (e.g. who is currently speaking) between
    utterance boundaries. Never drives an LLM call by itself -- only a
    completed ConversationEvent, or a forced-intervention rule match, does
    that (core.orchestrator.Orchestrator.handle_event).
    """

    speaker_id: str
    kind: Literal["started_speaking", "stopped_speaking"]
    timestamp: float
    channel_id: str
