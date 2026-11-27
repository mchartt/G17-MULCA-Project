"""
Starting with Cadence on Discord without commands (DECISIONS.md, 27/11).

    greeting_channel()  Cadence was just added to a server: where to say how
                        to start (the server's system channel, else the first
                        text channel it may write in).
    VoiceOffer          right after a pasted link linked a channel, one click
                        lets Cadence listen to the group's voice calls: a
                        button when the server has one voice channel, a menu
                        when it has more. It does what /coordinator voice
                        does (CoordinatorBridge.serve_voice) and tells the
                        channel who turned it on. /coordinator voice still works.

The view is not persistent: after a bot restart the old buttons stop
answering, and /coordinator voice is the way (said in the help).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from .bridge import CoordinatorBridge

logger = logging.getLogger(__name__)

GUILD_WELCOME = (
    "Hi, I'm **Cadence**, your group's project coordinator. To start:\n"
    "1. In the web app, open **Connect Slack or Discord** and press **Copy link**.\n"
    "2. Paste that link in the channel where your group talks. I answer there when it is linked.\n"
    "Then talk as usual: I step in only when something needs an owner, a date or a decision."
)
VOICE_OFFER = "Want me to listen to your voice calls too? I keep the transcript and turn what you decide into cards. I speak only if you call me by name."
OFFER_SECONDS = 24 * 3600


def greeting_channel(guild: Any) -> Any | None:
    """The server's system channel if Cadence may write there, else the first text channel it may."""
    me = getattr(guild, "me", None)

    def writable(channel: Any) -> bool:
        if channel is None or me is None:
            return False
        try:
            return bool(channel.permissions_for(me).send_messages)
        except Exception:
            return False

    system = getattr(guild, "system_channel", None)
    if writable(system):
        return system
    for channel in getattr(guild, "text_channels", []) or []:
        if writable(channel):
            return channel
    return None


def voice_channels(guild: Any) -> list[Any]:
    return list(getattr(guild, "voice_channels", None) or [])


class VoiceOffer(discord.ui.View):
    """One click: Cadence listens to the call in this voice channel."""

    def __init__(self, bridge: "CoordinatorBridge", channels: list[Any]) -> None:
        super().__init__(timeout=OFFER_SECONDS)
        self._bridge = bridge
        if len(channels) == 1:
            only = channels[0]
            button = discord.ui.Button(
                label=f"Listen to calls in {only.name}"[:80], style=discord.ButtonStyle.primary, emoji="🔊"
            )

            async def pressed(interaction: discord.Interaction) -> None:
                await self.turn_on(interaction, only)

            button.callback = pressed
            self.add_item(button)
        else:
            menu = discord.ui.ChannelSelect(
                channel_types=[discord.ChannelType.voice, discord.ChannelType.stage_voice],
                placeholder="Pick the voice channel your group uses",
                min_values=1,
                max_values=1,
            )

            async def picked(interaction: discord.Interaction) -> None:
                chosen = menu.values[0]
                guild = interaction.guild
                voice = guild.get_channel(chosen.id) if guild is not None else None
                await self.turn_on(interaction, voice or chosen)

            menu.callback = picked
            self.add_item(menu)

    async def turn_on(self, interaction: discord.Interaction, voice: Any) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        answer = await self._bridge.serve_voice(interaction, voice)
        await interaction.followup.send(answer, ephemeral=True)
        if answer.startswith("Cadence now listens"):
            # Everyone in the channel sees that voice is on, and who turned it on.
            self.stop()
            try:
                who = getattr(interaction.user, "display_name", "someone")
                await interaction.message.edit(
                    content=f"🔊 Cadence listens to the calls in {getattr(voice, 'mention', 'the voice channel')} "
                    f"(turned on by {who}). `/coordinator voice` changes the channel.",
                    view=None,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                logger.exception("Could not update the voice offer")
