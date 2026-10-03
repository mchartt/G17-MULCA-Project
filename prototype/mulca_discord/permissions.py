"""
What a bot is missing in a channel, as Discord permission names -- shared by
the preflight check and /mulca status, so both report the same thing.
"""

from __future__ import annotations

TEXT_PERMISSIONS = ("view_channel", "send_messages", "read_message_history")
VOICE_PERMISSIONS = ("connect", "speak", "use_voice_activation")


def missing_permissions(channel, member, *, voice: bool) -> list[str]:
    """The permissions `member` lacks in `channel` to serve it."""

    permissions = channel.permissions_for(member)
    wanted = VOICE_PERMISSIONS if voice else TEXT_PERMISSIONS
    return [name for name in wanted if not getattr(permissions, name)]
