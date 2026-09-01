"""Plain-code trigger-variable computation (BLUEPRINT.md §2 step 3).

No LLM call happens in this module.
"""
from collections import Counter


def gini_index(counts: list) -> float:
    """Gini index over per-speaker message counts. 0 = perfectly equal
    participation, close to 1 = one speaker dominates."""
    if not counts:
        return 0.0
    counts = sorted(counts)
    n = len(counts)
    if n == 1:
        return 0.0
    total = sum(counts)
    if total == 0:
        return 0.0
    cumulative = sum((i + 1) * c for i, c in enumerate(counts))
    return (2 * cumulative) / (n * total) - (n + 1) / n


def compute_trigger_variables(history: list, bot_user_id: str, roster: dict = None) -> dict:
    """`history` is the WM's list of ConversationEvent. Excludes the bot's own
    replies (bot_user_id) from participation stats -- the bot isn't a
    "participant" to balance against, and including it would corrupt
    who's-quiet detection. Only text events count toward participation stats
    for now -- SpeechActivityEvent-derived variables (e.g. current speaker)
    are the audio adapter's addition, see BLUEPRINT.md §6.

    `roster` ({user_id: display_name}) lets a participant who is present but
    has said nothing yet still show up with a count of 0, rather than being
    invisible until their first message -- without this, gini_index reads as
    "no imbalance" simply because a second/third participant hasn't spoken
    yet, understating what's actually going on.

    Counts and shares are keyed by display name (falling back to speaker_id
    when no display name is known) so the intervention agent can refer to
    people the same way they appear in the conversation transcript it's also
    given -- a known, accepted limitation of this prototype is that two
    participants sharing an identical display name would be conflated.
    """
    spoken_events = [event for event in history if event.speaker_id != bot_user_id]
    counts = Counter(event.label() for event in spoken_events)

    spoken_ids = {event.speaker_id for event in spoken_events}
    for participant_id, display_name in (roster or {}).items():
        if participant_id != bot_user_id and participant_id not in spoken_ids:
            counts.setdefault(display_name, 0)

    total = sum(counts.values())
    shares = {name: (count / total if total else 0.0) for name, count in counts.items()}
    return {
        "gini_index": gini_index(list(counts.values())),
        "message_count": len(spoken_events),
        "participant_message_counts": dict(counts),
        "participant_shares": shares,
    }
