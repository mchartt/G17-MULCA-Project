"""
MULCA's slash commands, registered by the primary bot only (several bots
registering the same commands would show each one several times in
Discord's "/" menu).

- /restart: anyone, in a channel MULCA serves -- restarts that channel's
  MULCA (fresh OpenAI connections, same memory).
- /mulca status|restart|stop|start: members with Manage Server, acting only
  on the bots in the server it's used in.
- /mulca link|unlink: members with Manage Server -- which channels a bot
  serves (links.py), with no code or config file involved.

The decisions are plain functions over BotManager (control, format_status,
restart_message), so they're testable without Discord; the command
callbacks only translate interactions to and from them.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from .links import Link
from .permissions import missing_permissions
from .runtime import BotManager, BotRuntime, BotStatus, RestartOutcome

logger = logging.getLogger(__name__)

# One /restart per channel per this many seconds: a restart takes a few
# seconds itself, and several people pressing it at once gain nothing.
RESTART_COOLDOWN_SECONDS = 30.0

ALL = "all"


# ----------------------------------------------------------------------
# What the commands do and say -- no Discord objects needed
# ----------------------------------------------------------------------


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "-"

    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h {seconds % 3600 // 60}m"


def restart_message(user_mention: str, outcome: RestartOutcome) -> str:
    if outcome.confirmed:
        return f"{user_mention} restarted MULCA here. It still remembers the conversation."

    return (
        f"{user_mention} restarted MULCA here. MUCA-Server didn't confirm "
        "it saved the conversation in time, so the last few messages may be "
        "missing from its memory."
    )


def format_status(statuses: list[BotStatus]) -> str:
    if not statuses:
        return "No MULCA bot is in this server."

    lines: list[str] = []
    for status in statuses:
        state = "paused" if status.paused else ("online" if status.online else "offline")
        latency = f", {status.latency_ms:.0f} ms" if status.latency_ms is not None else ""
        lines.append(
            f"**{status.name}**: {state}{latency}, up {_duration(status.uptime_seconds)}"
            + (f", {status.dm_sessions} open DM session(s)" if status.dm_sessions else "")
        )

        if not status.links:
            lines.append("  no channel linked in this server (`/mulca link`)")

        for link in status.links:
            voice = (
                f" + <#{link.voice_channel_id}>"
                + (" (in voice)" if link.in_voice else "")
                if link.voice_channel_id is not None
                else ""
            )
            session = (
                f"session open for {_duration(link.session_age_seconds)}"
                if link.session_open
                else "no open session (opens on the next message)"
            )
            closed = (
                f", last ended with code {link.last_close_code}"
                if link.last_close_code is not None
                else ""
            )
            lines.append(f"  <#{link.text_channel_id}>{voice}: {session}{closed}")
            lines.extend(f"  - {problem}" for problem in link.problems)

    return "\n".join(lines)


async def control(
    manager: BotManager,
    action: str,
    target: str | None,
    guild_id: int,
) -> str:
    """/mulca restart|stop|start, for `target` ("all" or a bot) in this server."""

    bots = manager.resolve(target, guild_id)
    if not bots:
        return f"No MULCA bot called {target!r} in this server."

    lines: list[str] = []
    for bot in bots:
        if action == "restart":
            outcomes = await bot.restart_all()
            unconfirmed = [
                f"<#{o.link.text_channel_id}>" for o in outcomes if not o.confirmed
            ]
            lines.append(
                f"**{bot.name}** restarted"
                + (
                    f" (save not confirmed for {', '.join(unconfirmed)})"
                    if unconfirmed
                    else ""
                )
                + "."
            )
        elif action == "stop":
            await bot.pause()
            lines.append(
                f"**{bot.name}** stopped: out of voice, not answering. "
                "`/mulca start` brings it back."
            )
        elif action == "start":
            await bot.resume()
            lines.append(f"**{bot.name}** started.")
        else:  # pragma: no cover - the command choices prevent it
            raise ValueError(action)

    return "\n".join(lines)


async def link_channels(
    *,
    bot: BotRuntime,
    guild_id: int,
    text_channel,
    voice_channel=None,
    post_voice_transcripts: bool = False,
    created_by: int | None = None,
) -> str:
    """/mulca link: check, save, put into effect, and say what happened."""

    guild = bot.client.get_guild(guild_id)
    bot_member = guild.get_member(bot.user_id) if guild is not None else None
    if bot_member is None:
        return f"**{bot.name}** isn't in this server."

    # The bot itself must be able to see the channels it's asked to serve.
    for channel in (text_channel, voice_channel):
        if channel is not None and not channel.permissions_for(bot_member).view_channel:
            return f"**{bot.name}** can't see <#{channel.id}>. Give it access first."

    link = Link(
        text_channel_id=text_channel.id,
        guild_id=guild_id,
        bot_id=bot.user_id,
        voice_channel_id=voice_channel.id if voice_channel is not None else None,
        post_voice_transcripts=post_voice_transcripts,
    )

    problems = bot.store.conflicts(link)
    if problems:
        return "Not linked: " + " ".join(problems)

    previous = bot.store.save(link, created_by=created_by)
    await bot.apply_link(link, previous)

    where = f"<#{text_channel.id}>" + (
        f" and <#{voice_channel.id}>" if voice_channel is not None else ""
    )
    lines = [
        (
            f"Updated: **{bot.name}** serves {where}."
            if previous is not None
            else f"Linked: **{bot.name}** now serves {where}."
        )
        + (" Spoken replies are also posted as text." if post_voice_transcripts else ""),
        "If MULCA was linked to this channel before, it still remembers that conversation.",
    ]

    warnings = [
        f"missing **{name}** in <#{channel.id}>"
        for channel, voice in ((text_channel, False), (voice_channel, True))
        if channel is not None
        for name in missing_permissions(channel, bot_member, voice=voice)
    ]
    if warnings:
        lines.append("It can't work fully yet: " + "; ".join(warnings) + ".")

    return "\n".join(lines)


async def unlink_channel(manager: BotManager, channel_id: int) -> str:
    """/mulca unlink: stop serving the link that owns this channel."""

    found = manager.link_for_channel(channel_id)
    if found is None:
        return f"<#{channel_id}> isn't linked to any MULCA bot."

    bot, link = found
    await bot.unlink(link)
    bot.store.remove(link.text_channel_id)

    return (
        f"Unlinked: **{bot.name}** no longer serves <#{link.text_channel_id}>"
        + (f" and <#{link.voice_channel_id}>" if link.voice_channel_id else "")
        + ". Its memory is kept: linking the channel again brings it back."
    )


# ----------------------------------------------------------------------
# Discord glue
# ----------------------------------------------------------------------


class MulcaGroup(app_commands.Group):
    """/mulca: hidden from members without Manage Server, and checked too."""

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        permissions = getattr(interaction.user, "guild_permissions", None)
        if permissions is None or not permissions.manage_guild:
            raise app_commands.MissingPermissions(["manage_guild"])
        return True


def install_commands(manager: BotManager) -> app_commands.CommandTree:
    primary = manager.primary
    tree = app_commands.CommandTree(primary.client)

    async def bot_choices(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        names = [ALL] + [
            bot.name for bot in manager.in_guild(interaction.guild_id or 0)
        ]
        return [
            app_commands.Choice(name=name, value=name)
            for name in names
            if current.lower() in name.lower()
        ][:25]

    # -- /restart -------------------------------------------------------

    @tree.command(
        name="restart",
        description="Restart MULCA in this channel. It keeps its memory.",
    )
    @app_commands.guild_only()
    @app_commands.checks.cooldown(
        1,
        RESTART_COOLDOWN_SECONDS,
        key=lambda interaction: interaction.channel_id,
    )
    async def restart(interaction: discord.Interaction) -> None:
        found = manager.link_for_channel(interaction.channel_id)
        if found is None:
            await interaction.response.send_message(
                "MULCA doesn't run in this channel.",
                ephemeral=True,
            )
            return

        bot, link = found
        await interaction.response.defer(thinking=True)
        outcome = await bot.restart_link(link)
        await interaction.followup.send(
            restart_message(interaction.user.mention, outcome),
        )

    # -- /mulca ... -----------------------------------------------------

    mulca = MulcaGroup(
        name="mulca",
        description="Control MULCA (needs Manage Server).",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @mulca.command(name="status", description="Show every MULCA bot in this server.")
    async def status(interaction: discord.Interaction) -> None:
        statuses = [
            bot.status(interaction.guild_id)
            for bot in manager.in_guild(interaction.guild_id)
        ]
        await interaction.response.send_message(format_status(statuses), ephemeral=True)

    @mulca.command(
        name="link",
        description="Make MULCA serve a text channel, and optionally a voice channel.",
    )
    @app_commands.describe(
        text="The text channel (default: this one). MULCA's memory belongs to it.",
        voice="A voice channel MULCA joins whenever someone is in it.",
        bot="Which MULCA bot (default: the main one).",
        transcripts="Also post what MULCA says out loud in the text channel.",
    )
    @app_commands.autocomplete(bot=bot_choices)
    async def link(
        interaction: discord.Interaction,
        text: discord.TextChannel | None = None,
        voice: discord.VoiceChannel | None = None,
        bot: str | None = None,
        transcripts: bool = False,
    ) -> None:
        text = text or interaction.channel
        if not isinstance(text, discord.TextChannel):
            await interaction.response.send_message(
                "Pick a text channel, or run this in one.",
                ephemeral=True,
            )
            return

        chosen = (
            [manager.primary]
            if bot is None or bot.strip().lower() == ALL
            else manager.resolve(bot, interaction.guild_id)
        )
        if not chosen:
            await interaction.response.send_message(
                f"No MULCA bot called {bot!r} in this server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await link_channels(
            bot=chosen[0],
            guild_id=interaction.guild_id,
            text_channel=text,
            voice_channel=voice,
            post_voice_transcripts=transcripts,
            created_by=interaction.user.id,
        )
        await interaction.followup.send(reply, ephemeral=True)

    @mulca.command(
        name="unlink",
        description="Stop MULCA serving a channel. Its memory is kept.",
    )
    @app_commands.describe(
        channel="The linked text or voice channel (default: this one).",
    )
    async def unlink(
        interaction: discord.Interaction,
        channel: discord.TextChannel | discord.VoiceChannel | None = None,
    ) -> None:
        channel_id = channel.id if channel is not None else interaction.channel_id
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await unlink_channel(manager, channel_id)
        await interaction.followup.send(reply, ephemeral=True)

    async def run_control(
        interaction: discord.Interaction,
        action: str,
        bot: str | None,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await control(manager, action, bot, interaction.guild_id)
        await interaction.followup.send(reply, ephemeral=True)

    @mulca.command(
        name="restart",
        description="Restart MULCA's connections. It keeps its memory.",
    )
    @app_commands.describe(bot="One bot, or all of them in this server (default).")
    @app_commands.autocomplete(bot=bot_choices)
    async def restart_bots(interaction: discord.Interaction, bot: str | None = None) -> None:
        await run_control(interaction, "restart", bot)

    @mulca.command(
        name="stop",
        description="Stop MULCA: it leaves voice and stops answering until started.",
    )
    @app_commands.describe(bot="One bot, or all of them in this server (default).")
    @app_commands.autocomplete(bot=bot_choices)
    async def stop(interaction: discord.Interaction, bot: str | None = None) -> None:
        await run_control(interaction, "stop", bot)

    @mulca.command(name="start", description="Start MULCA again after /mulca stop.")
    @app_commands.describe(bot="One bot, or all of them in this server (default).")
    @app_commands.autocomplete(bot=bot_choices)
    async def start(interaction: discord.Interaction, bot: str | None = None) -> None:
        await run_control(interaction, "start", bot)

    tree.add_command(mulca)

    # -- errors -----------------------------------------------------------

    @tree.error
    async def on_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            message = (
                f"MULCA was just restarted here; try again in "
                f"{error.retry_after:.0f} s."
            )
        elif isinstance(error, app_commands.MissingPermissions):
            message = "Only members with the Manage Server permission can use /mulca."
        else:
            logger.error(
                "Slash command %s failed",
                interaction.command.qualified_name if interaction.command else "?",
                exc_info=error,
            )
            message = "That didn't work; the error is in MULCA's logs."

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    # -- registration -------------------------------------------------------

    async def sync_guild(guild: discord.abc.Snowflake) -> None:
        # Per server, not global: a global sync takes up to an hour to show
        # up, a server's is immediate.
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)

    async def sync_all(runtime: BotRuntime) -> None:
        for guild in runtime.client.guilds:
            try:
                await sync_guild(guild)
                logger.info("Slash commands registered in %s", guild)
            except Exception:
                logger.exception("Could not register slash commands in %s", guild)

    primary.after_ready.append(sync_all)

    @primary.client.event
    async def on_guild_join(guild: discord.Guild) -> None:
        try:
            await sync_guild(guild)
        except Exception:
            logger.exception("Could not register slash commands in %s", guild)

    return tree
