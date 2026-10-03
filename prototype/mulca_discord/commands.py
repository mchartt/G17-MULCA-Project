"""
MULCA's slash commands, registered by the primary bot only (several bots
registering the same commands would show each one several times in
Discord's "/" menu).

- /restart: anyone, in a channel MULCA serves -- restarts that channel's
  MULCA (fresh OpenAI connections, same memory).
- /mulca status|restart|stop|start: members with Manage Server, acting only
  on the bots in the server it's used in.

The decisions are plain functions over BotManager (control, format_status,
restart_message), so they're testable without Discord; the command
callbacks only translate interactions to and from them.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands

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
            lines.append("  no channel (none of its configured text channels is visible)")

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
            lines.append(f"  {link.name}: <#{link.text_channel_id}>{voice}; {session}{closed}")
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
            unconfirmed = [o.instance.name for o in outcomes if not o.confirmed]
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

        bot, instance = found
        await interaction.response.defer(thinking=True)
        outcome = await bot.restart_link(instance)
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
        statuses = [bot.status() for bot in manager.in_guild(interaction.guild_id)]
        await interaction.response.send_message(format_status(statuses), ephemeral=True)

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
