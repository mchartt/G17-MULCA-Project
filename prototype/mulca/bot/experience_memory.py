"""experience_memory (BLUEPRINT.md §4's CoALA mapping): the episodic
long-term memory type -- what happened, when, why. Backed by `EpisodicLog`;
this module is the one place code should read/write it through, rather than
scattered direct ORM calls. A thin wrapper, not a renamed model -- renaming
`EpisodicLog` itself would need a migration and touch every reference for no
functional gain.

Distinct from `WorkingMemorySnapshot` (BLUEPRINT.md §11.1), which is *not*
part of experience_memory -- that's WM continuity ("what should I remember
right now"), not the episodic audit trail ("what happened and why").
"""
from asgiref.sync import sync_to_async

from .models import EpisodicLog


async def log(record: dict) -> None:
    await sync_to_async(EpisodicLog.objects.create)(**record)


def _fetch_recent_rows(channel_id: str, limit: int) -> list:
    # Recency-window retrieval, not relevance-ranked (BLUEPRINT.md §12 --
    # deliberately not "a real RAG pipeline"): the most recent `limit` rows
    # for this channel, oldest first, regardless of what's actually being
    # asked about.
    rows = list(
        EpisodicLog.objects.filter(channel_id=channel_id).order_by("-timestamp")[:limit]
    )
    rows.reverse()
    return rows


async def recall_recent(channel_id: str, limit: int) -> list:
    """Returns dicts (not model instances, to keep core/ Django-free):
    {speaker, content, main_llm_output}, chronological order, skipping
    management-cycle rows (BLUEPRINT.md §12's `provide_summary`/
    `needs_history` retrieval) -- those have no incoming_event_content and
    aren't useful raw material for a user-facing answer."""
    rows = await sync_to_async(_fetch_recent_rows)(channel_id, limit)
    return [
        {
            "speaker": row.incoming_event_speaker,
            "content": row.incoming_event_content,
            "main_llm_output": row.main_llm_output,
        }
        for row in rows
        if row.intervention_path != "management_cycle"
    ]
