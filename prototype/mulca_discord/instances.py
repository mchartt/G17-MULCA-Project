"""
Discord-specific: which text channel + voice channel + participant roster
make up one MULCA instance's persistent memory.

This is deliberately the only place that knows what a "channel" or a
"participant" is on the Discord side -- MUCA-Server never sees any of this,
only the conversation_id derived from it (MulcaInstance.conversation_id),
same as it never sees "Discord" at all elsewhere in this adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "instances.yaml"


@dataclass(frozen=True, slots=True)
class MulcaInstance:
    """
    One bot's scope: a text channel, its paired voice channel (once audio
    exists -- None until then), and the participants who belong to it.

    A stable `name` (not either channel id) is what conversation_id derives
    from, so text and voice share one scope/one memory once voice is added --
    the pairing itself is a config decision, not something inferable from
    the channel ids alone.
    """

    name: str
    text_channel_id: int
    voice_channel_id: int | None = None

    # Documents team membership and (once there are per-instance bot tokens)
    # is what a DM's own bot naturally scopes to -- not a hard allowlist:
    # a DM is still handled from anyone, per BLUEPRINT.md's "open to DMs
    # from any individual user." The live channel.members roster (see
    # discord_client.py's _roster()) is still what actually drives
    # participation trigger variables; this is instance ownership, not a
    # substitute for that.
    participant_ids: frozenset[int] = field(default_factory=frozenset)

    @property
    def conversation_id(self) -> str:
        return f"instance:{self.name}"

    def owns_channel(self, channel_id: int) -> bool:
        # Explicit "is not None" guard: without it, an unconfigured
        # voice_channel_id (None) would wrongly match a channel_id of None.
        return channel_id == self.text_channel_id or (
            self.voice_channel_id is not None
            and channel_id == self.voice_channel_id
        )


def load_instances(path: Path = DEFAULT_CONFIG_PATH) -> list[MulcaInstance]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    return [
        MulcaInstance(
            name=entry["name"],
            text_channel_id=int(entry["text_channel_id"]),
            voice_channel_id=(
                int(entry["voice_channel_id"])
                if entry.get("voice_channel_id") is not None
                else None
            ),
            participant_ids=frozenset(
                int(participant_id)
                for participant_id in entry.get("participant_ids", [])
            ),
        )
        for entry in data.get("instances", [])
    ]


def instance_for_channel(
    instances: list[MulcaInstance],
    channel_id: int,
) -> MulcaInstance | None:
    for instance in instances:
        if instance.owns_channel(channel_id):
            return instance

    return None
