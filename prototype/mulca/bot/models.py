"""Episodic memory persistence (BLUEPRINT.md §4.2). Logged even when
intervention_path == "none", so "the agent chose not to speak" is auditable
too."""
from django.db import models


class EpisodicLog(models.Model):
    timestamp = models.FloatField()
    channel_id = models.CharField(max_length=64)
    incoming_event_speaker = models.CharField(max_length=128)
    incoming_event_content = models.TextField()
    trigger_variables_snapshot = models.JSONField()
    intervention_path = models.CharField(max_length=16)  # "none" | "strategy" | "forced"
    strategy_id = models.CharField(max_length=64, null=True, blank=True)
    prompt_fragment = models.TextField(null=True, blank=True)
    main_llm_output = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["timestamp"]


class WorkingMemorySnapshot(models.Model):
    """Startup/shutdown persistence (BLUEPRINT.md §11.1) -- separate from
    EpisodicLog: this is a single, overwritten current-state row per instance
    (keyed by its registered channel), purely to seed the next boot's WM.
    EpisodicLog stays the append-only audit trail; this answers "what should
    I remember right now," not "what happened and why."

    Only the "group" scope is ever persisted here -- a DM's WM is never
    written here, same as it's never written to EpisodicLog (BLUEPRINT.md's
    "Channel/instance scoping" section).
    """
    channel_id = models.CharField(max_length=64, unique=True)
    history_summary = models.TextField(blank=True, default="")
    participant_roles_summary = models.TextField(blank=True, default="")
    history_tail = models.JSONField(default=list)  # serialized ConversationEvent dicts
    total_message_count = models.IntegerField(default=0)
    updated_at = models.FloatField()
