"""
MULCA's slash commands, registered by the primary bot only (several bots
registering the same commands would show each one several times in
Discord's "/" menu).

- /restart: anyone, in a channel MULCA serves -- restarts that channel's
  MULCA (fresh OpenAI connections, same memory).
- /listen: anyone, in a channel MULCA serves -- "toggle" mode only
  (MUCA_LISTENING_MODE=toggle): a toggle, same command starts and stops a
  listening window (the server decides which, not the client). A no-op
  (but still succeeds) if that channel's MULCA is running ambient or
  "transcribe" mode (the latter arms hands-free, via a spoken wake phrase,
  instead).
- /help: anyone, anywhere -- what MULCA is and how to talk to it (text,
  voice, starting/ending a "wake" voice conversation). Static; doesn't
  depend on any one channel's own configuration.
- /diary: anyone, anywhere -- the link to the post-session diary form.
- /mulca button: members with Manage Server -- posts a persistent "Talk to
  MULCA" button (ListenView) in the channel; anyone can press it, same
  effect as /listen. Survives a bot restart (a fixed custom_id, registered
  once via add_view(), not per-message state).
- /mulca status|restart|stop|start: members with Manage Server, acting only
  on the bots in the server it's used in.
- /mulca link|unlink|dms: members with Manage Server -- which channels a
  bot serves (links.py), with no code or config file involved, and whether
  the people of a channel may DM it (off by default).
- /mulca announce: members with Manage Server -- re-posts the welcome/
  guidelines message (messages.INTRO_MESSAGE) in a linked channel, or (with
  all:true) every linked channel in the server. /mulca link already posts
  it once, automatically, the first time a channel is newly linked; this
  is for re-sending it later (e.g. to channels linked before the message
  existed).
- /mulca help: members with Manage Server -- posts HELP_MESSAGE (same text
  as the member-facing /help) in a linked channel, or (all:true) every
  linked channel -- unlike /help, not ephemeral, so it's a visible part of
  a channel's setup sequence (announce, then help, then greet) rather than
  something a member has to ask for themselves.
- /mulca voiceupdate: members with Manage Server -- posts VOICE_UPDATE_
  MESSAGE (how to start/stop MULCA in voice) in a linked channel, or
  (all:true) every one. For announcing that change; /mulca announce's
  intro stays as it is.
- /mulca greet: members with Manage Server -- posts the first-session
  variant of the reminder (messages.FIRST_SESSION_MESSAGE, no "welcome
  back" framing) once, for a channel (or with all:true, every linked
  channel) about to start its first real session, and resets the
  reminder's own cooldown so the automatic one (BotRuntime.on_message)
  doesn't also post again right away.
- /mulca model: members with Manage Server -- the realtime model of every
  MUCA, or of one bot. Like /mulca bot, it acts on the whole deployment.
- /mulca costalert: members with Manage Server -- MUCA-Server's own
  cost-alert webhook/$ threshold (usage_report.py). Deployment-wide, like
  /mulca model, but nothing restarts for it.
- /mulca export: members with Manage Server -- a linked channel's episodic
  log (every message and spoken turn, what MULCA decided and said, voice
  call and wake session starts/ends) as CSV, or with all:true every linked
  channel's, zipped. Read from MUCA-Server, gated on MUCA_ADMIN_TOKEN.
- /mulca limit set|clear, /mulca usage: members with Manage Server -- how
  many USD a bot, every bot, or all bots together may spend per day, week
  and month (usage.py), how much they spent, and on what. Deployment-wide
  too. The only place costs are shown: replies are ephemeral, and what the
  bots tell their channels never mentions money.
- /mulca bot add|remove|list: members with Manage Server -- more bot
  accounts, run by this same process. These act on the whole deployment,
  not just the server they're used in (see deploy/README.md, Security).

The decisions are plain functions over BotManager (control, format_status,
restart_message), so they're testable without Discord; the command
callbacks only translate interactions to and from them.
"""

from __future__ import annotations

import io
import logging
import os
import re
import time
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal

import discord
from discord import app_commands

from . import courses, messages
from .links import BotRecord, Link
from .messages import DIARY_FORM_URL, DIARY_MESSAGE
from .muca_client import (
    MucaConnectionLost,
    fetch_episodic_export,
    set_server_cost_alert,
    set_server_model,
)
from .permissions import missing_permissions
from .runtime import LIMIT, AmbiguousBotName, BotManager, BotRuntime, BotStatus, RestartOutcome
from .usage import EACH, KINDS, POOL, POOL_FACTOR, UsageMeter, bot_scope

logger = logging.getLogger(__name__)

# One /restart per channel per this many seconds: a restart takes a few
# seconds itself, and several people pressing it at once gain nothing.
RESTART_COOLDOWN_SECONDS = 30.0

ALL = "all"

# Discord rejects longer messages; replies that grow with the number of bots
# (status, usage, the bot list) are sent in several.
DISCORD_MESSAGE_LIMIT = 2000


def split_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """`text` in chunks of at most `limit` characters, cut between lines."""

    chunks: list[str] = []
    current: str | None = None
    for line in text.split("\n"):
        if len(line) > limit:  # Only an absurdly long line is cut.
            if current is not None:
                chunks.append(current)
            *pieces, line = [line[i : i + limit] for i in range(0, len(line), limit)]
            chunks.extend(pieces)
            current = None
        if current is not None and len(current) + 1 + len(line) <= limit:
            current += "\n" + line
        else:
            if current is not None:
                chunks.append(current)
            current = line
    chunks.append(current or "")
    return chunks


async def send_long(interaction: discord.Interaction, text: str) -> None:
    """An ephemeral reply, after a defer, in as many messages as it takes."""

    # Discord rejects empty messages too.
    for chunk in [c for c in split_message(text) if c.strip()] or ["(nothing to show)"]:
        await interaction.followup.send(chunk, ephemeral=True)


def _ambiguous_bot_message(exc: AmbiguousBotName) -> str:
    ids = ", ".join(f"`{bot.user_id}`" for bot in exc.matches)
    return (
        f"{len(exc.matches)} bots in this server are named {exc.name!r} -- "
        f"use one's id instead: {ids}."
    )


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


def listening_toggle_message(bot_name: str, now_listening: bool | None) -> str:
    """
    The confirmation for /listen and the button, which both just toggled
    "toggle" mode's listening window. `now_listening` is whatever
    MUCA-Server actually reported back (BotRuntime.arm_listening's
    return): True/False for the state it resolved to, or None if nothing
    came back in time -- typically this channel isn't in "toggle" mode at
    all, since the server never replies to this in ambient or "transcribe"
    mode.
    """

    if now_listening is True:
        return f"🎙️ {bot_name} is now listening -- go ahead."
    if now_listening is False:
        return f"🔇 {bot_name} has stopped listening."

    return (
        f"Pressed, but {bot_name} didn't confirm a new listening state -- "
        "this channel may not be in \"toggle\" mode "
        "(`/mulca link mode:toggle`)."
    )


# /help: deliberately static, not tailored to one channel's own listening
# mode (toggle/transcribe/wake/ambient, set per-link by an admin) -- a
# member asking for help may not even be in a channel MULCA is linked to
# yet. Describes the voice behaviour most worth explaining ("wake": say
# its name to start, a closing phrase to end), since that one is the least
# self-explanatory; a channel in a different mode works simply enough
# (ambient: it just listens; toggle/transcribe: a button or /listen).
HELP_MESSAGE = (
    "**What MULCA is**\n"
    "MULCA is a tutoring assistant here to support your group's project "
    "work, in both text and voice.\n\n"
    "**How to talk to it**\n"
    "*In text*: mention it by name (e.g. \"assistant\", \"MULCA\", \"bot\" "
    "or \"chatbot\"), or reply to one of its messages. It may also speak "
    "up on its own sometimes, if it thinks it can contribute.\n\n"
    "*In voice*: say **\"MULCA start\"** (or \"assistant start\") when you "
    "want to ask it questions -- you can ask right away, e.g. \"MULCA "
    "start, what's our next deadline?\". It will start actively responding "
    "to the conversation, until it goes back into bystander mode. Say "
    "\"MULCA stop\" (or something like \"thanks MULCA\", \"that's all\" or "
    "\"go to sleep\") to end it. It also goes back on its own after a "
    "while if you're no longer talking to it."
)


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
        lines.append(f"  models: main {status.models[0]}, intervention {status.models[1]}")

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
            dms = ", DMs on" if link.allow_dms else ""
            lines.append(f"  <#{link.text_channel_id}>{voice}: {session}{closed}{dms}")
            lines.extend(f"  - {problem}" for problem in link.problems)

    return "\n".join(lines)


async def control(
    manager: BotManager,
    action: str,
    target: str | None,
    guild_id: int,
) -> str:
    """/mulca restart|stop|start, for `target` ("all" or a bot) in this server."""

    try:
        bots = manager.resolve(target, guild_id)
    except AmbiguousBotName as exc:
        return _ambiguous_bot_message(exc)

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
    allow_dms: bool | None = None,
    listening_mode: str | None = None,
    created_by: int | None = None,
) -> str:
    """
    /mulca link: check, save, put into effect, and say what happened.
    `allow_dms`/`listening_mode` None keeps what the channel had (off, and
    unset -- deferring to MUCA-Server's own default -- for a new link).
    """

    guild = bot.client.get_guild(guild_id)
    bot_member = guild.get_member(bot.user_id) if guild is not None else None
    if bot_member is None:
        return f"**{bot.name}** isn't in this server."

    # The bot itself must be able to see the channels it's asked to serve.
    for channel in (text_channel, voice_channel):
        if channel is not None and not channel.permissions_for(bot_member).view_channel:
            return f"**{bot.name}** can't see <#{channel.id}>. Give it access first."

    existing = bot.store.link_for_channel(text_channel.id)
    if allow_dms is None:
        allow_dms = existing.allow_dms if existing is not None else False
    if listening_mode is None:
        listening_mode = existing.listening_mode if existing is not None else ""

    link = Link(
        text_channel_id=text_channel.id,
        guild_id=guild_id,
        bot_id=bot.user_id,
        voice_channel_id=voice_channel.id if voice_channel is not None else None,
        post_voice_transcripts=post_voice_transcripts,
        allow_dms=allow_dms,
        listening_mode=listening_mode,
    )

    problems = bot.store.conflicts(link)
    if problems:
        return "Not linked: " + " ".join(problems)

    previous = bot.store.save(link, created_by=created_by)
    await bot.apply_link(link, previous)

    if previous is None:
        # A brand-new link, not a settings change to one that already
        # existed -- the group's first time seeing this channel, so this
        # is the moment to greet them, not every later /mulca link tweak.
        # _channel_for_bot: text_channel came from the slash command's own
        # interaction, always bound to the primary bot's connection --
        # re-resolved through `bot`'s own client in case this link is for
        # a different bot account (one per simultaneous voice channel).
        await messages.post(_channel_for_bot(bot, text_channel), messages.INTRO_MESSAGE)

    where = f"<#{text_channel.id}>" + (
        f" and <#{voice_channel.id}>" if voice_channel is not None else ""
    )
    lines = [
        (
            f"Updated: **{bot.name}** serves {where}."
            if previous is not None
            else f"Linked: **{bot.name}** now serves {where}."
        )
        + (" Spoken replies are also posted as text." if post_voice_transcripts else "")
        + (
            " People who can see this channel may DM it."
            if allow_dms
            else " DMs are off (`/mulca dms` turns them on)."
        )
        + (
            " Listening mode: toggle (`/listen` toggles a window)."
            if listening_mode == "toggle"
            else (
                " Listening mode: transcribe (say \"assistant\" to open a window)."
                if listening_mode == "transcribe"
                else (
                    " Listening mode: wake (say \"assistant\" and MULCA joins"
                    " the discussion until it goes quiet)."
                    if listening_mode == "wake"
                    else (
                        " Listening mode: wake_v2 (wake, with the fixes from"
                        " the October tests)."
                        if listening_mode == "wake_v2"
                        else ""
                    )
                )
            )
        ),
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


async def _post(channel, text: str) -> str | None:
    """Posts text; None on success, or a short description of why it failed."""

    try:
        await channel.send(text)
        return None
    except Exception as exc:
        logger.warning("Could not post in %s", channel, exc_info=True)
        return str(exc) or type(exc).__name__


def _channel_for_bot(bot: BotRuntime, channel):
    """
    The channel object to actually post through -- re-resolved via the bot
    that owns this channel's link, not necessarily the one a slash
    command's own interaction handed in. Slash commands are only ever
    registered and handled by the primary bot, so a channel option Discord
    resolves for one is always bound to the primary bot's own connection,
    regardless of which bot (in a multi-bot deployment, one account per
    simultaneous voice channel) actually serves that channel. Found live:
    posting through that interaction-resolved object sent via the primary
    bot's own token, which 403'd (Missing Access) on a private channel
    only the serving bot's account had actually been added to -- MULCA
    still replied there fine conversationally, since a normal reply always
    goes out through the serving bot's own live message event, never the
    primary bot at all. Falls back to the given channel if the owning
    bot's own client doesn't have it cached, rather than failing outright.
    """

    return bot.client.get_channel(channel.id) or channel


async def announce_intro(manager: BotManager, channel) -> str:
    """
    /mulca announce: re-post messages.INTRO_MESSAGE in a linked channel --
    /mulca link already posts it once, automatically, on a brand-new link;
    this is for sending it again later (e.g. to channels linked before the
    message existed, which is why this exists at all).
    """

    if channel is None:
        return "Pick a text channel, or run this in one."

    found = manager.link_for_channel(channel.id)
    if found is None:
        return f"MULCA doesn't serve <#{channel.id}> (`/mulca link` it first)."

    bot, _link = found
    error = await _post(_channel_for_bot(bot, channel), messages.INTRO_MESSAGE)
    if error is not None:
        # Found live: this used to unconditionally say "Posted", even when
        # channel.send() itself failed (that specific channel's own
        # problem, not a general permissions issue -- MULCA still replied
        # normally there) -- the admin had no way to tell the command
        # silently did nothing.
        return f"Could not post in <#{channel.id}>: {error}"
    return f"Posted in <#{channel.id}>."


async def _post_everywhere(manager: BotManager, guild_id: int, text: str) -> str:
    """Posts `text` in every text channel linked (by any bot) in this server."""

    posted = []
    failed = []
    for bot in manager.resolve(None, guild_id):
        for link in bot.links():
            if link.guild_id != guild_id:
                continue
            channel = bot.client.get_channel(link.text_channel_id)
            if channel is None:
                failed.append(f"<#{link.text_channel_id}> (channel not found)")
                continue
            error = await _post(channel, text)
            if error is not None:
                failed.append(f"<#{link.text_channel_id}> ({error})")
            else:
                posted.append(f"<#{link.text_channel_id}>")

    if not posted and not failed:
        return "No linked channel in this server."
    lines = []
    if posted:
        lines.append("Posted in: " + ", ".join(posted) + ".")
    if failed:
        lines.append("Could not post in: " + ", ".join(failed) + ".")
    return "\n".join(lines)


async def announce_intro_everywhere(manager: BotManager, guild_id: int) -> str:
    """/mulca announce all:true -- messages.INTRO_MESSAGE in every linked channel here."""

    return await _post_everywhere(manager, guild_id, messages.INTRO_MESSAGE)


async def post_help(manager: BotManager, channel) -> str:
    """
    /mulca help: posts messages.HELP_MESSAGE publicly in a linked channel --
    unlike the member-facing /help (ephemeral, works anywhere), this is for
    an admin to broadcast it as a visible step of a channel's setup, e.g.
    right after /mulca announce.
    """

    if channel is None:
        return "Pick a text channel, or run this in one."

    found = manager.link_for_channel(channel.id)
    if found is None:
        return f"MULCA doesn't serve <#{channel.id}> (`/mulca link` it first)."

    bot, _link = found
    error = await _post(_channel_for_bot(bot, channel), HELP_MESSAGE)
    if error is not None:
        return f"Could not post in <#{channel.id}>: {error}"
    return f"Posted in <#{channel.id}>."


async def post_help_everywhere(manager: BotManager, guild_id: int) -> str:
    """/mulca help all:true -- messages.HELP_MESSAGE in every linked channel here."""

    return await _post_everywhere(manager, guild_id, HELP_MESSAGE)


async def post_voice_update(manager: BotManager, channel) -> str:
    """/mulca voiceupdate: messages.VOICE_UPDATE_MESSAGE in a linked channel."""

    if channel is None:
        return "Pick a text channel, or run this in one."

    found = manager.link_for_channel(channel.id)
    if found is None:
        return f"MULCA doesn't serve <#{channel.id}> (`/mulca link` it first)."

    bot, _link = found
    error = await _post(_channel_for_bot(bot, channel), messages.VOICE_UPDATE_MESSAGE)
    if error is not None:
        return f"Could not post in <#{channel.id}>: {error}"
    return f"Posted in <#{channel.id}>."


async def post_voice_update_everywhere(manager: BotManager, guild_id: int) -> str:
    """/mulca voiceupdate all:true -- in every linked channel here."""

    return await _post_everywhere(manager, guild_id, messages.VOICE_UPDATE_MESSAGE)


async def greet_first_session_everywhere(manager: BotManager, guild_id: int) -> str:
    """
    /mulca greet all:true -- messages.FIRST_SESSION_MESSAGE in every linked
    channel here, same per-channel bookkeeping as the single-channel
    version (BotRuntime.post_first_session_greeting): resets the
    reminder's cooldown without counting as a real session.
    """

    posted = []
    failed = []
    for bot in manager.resolve(None, guild_id):
        for link in bot.links():
            if link.guild_id != guild_id:
                continue
            channel = bot.client.get_channel(link.text_channel_id)
            if channel is None:
                failed.append(f"<#{link.text_channel_id}> (channel not found)")
                continue
            error = await bot.post_first_session_greeting(channel, link.conversation_id)
            if error is not None:
                failed.append(f"<#{link.text_channel_id}> ({error})")
            else:
                posted.append(f"<#{link.text_channel_id}>")

    if not posted and not failed:
        return "No linked channel in this server."
    lines = []
    if posted:
        lines.append("Posted in: " + ", ".join(posted) + ".")
    if failed:
        lines.append("Could not post in: " + ", ".join(failed) + ".")
    return "\n".join(lines)


async def greet_first_session(manager: BotManager, channel) -> str:
    """
    /mulca greet: post messages.FIRST_SESSION_MESSAGE once, right after a
    channel is linked and announced, for its first-ever session -- and
    resets the reminder's own cooldown so the automatic one
    (BotRuntime.on_message) doesn't also post its own, differently-worded
    one right away.
    """

    if channel is None:
        return "Pick a text channel, or run this in one."

    found = manager.link_for_channel(channel.id)
    if found is None:
        return f"MULCA doesn't serve <#{channel.id}> (`/mulca link` it first)."

    bot, link = found
    error = await bot.post_first_session_greeting(
        _channel_for_bot(bot, channel), link.conversation_id
    )
    if error is not None:
        return f"Could not post in <#{channel.id}>: {error}"
    return f"Posted in <#{channel.id}>."


async def set_dms(manager: BotManager, channel_id: int, enabled: bool) -> str:
    """/mulca dms: let the people of one linked channel DM its bot, or not."""

    found = manager.link_for_channel(channel_id)
    if found is None:
        return f"<#{channel_id}> isn't linked to any MULCA bot; `/mulca link` it first."

    bot, link = found
    bot.store.save(replace(link, allow_dms=enabled))
    if not enabled:
        await bot.close_dms_of(link)

    if enabled:
        return (
            f"DMs on: people who can see <#{link.text_channel_id}> may now DM "
            f"**{bot.name}**, and it remembers this channel's conversation there."
        )
    return (
        f"DMs off for <#{link.text_channel_id}>: its people can no longer DM "
        f"**{bot.name}**, unless another DM-enabled channel of it lets them."
    )


async def set_mode(manager: BotManager, mode: str, target: str | None, guild_id: int) -> str:
    """/mulca mode: every link of every bot here (or of one bot) switched to `mode`, live."""

    try:
        bots = manager.resolve(target, guild_id)
    except AmbiguousBotName as exc:
        return _ambiguous_bot_message(exc)

    if not bots:
        return f"No MULCA bot called {target!r} in this server."

    changed = []
    for bot in bots:
        for link in bot.links():
            if link.guild_id != guild_id or link.listening_mode == mode:
                continue
            updated = replace(link, listening_mode=mode)
            await bot.apply_link(updated, bot.store.save(updated))
            changed.append(f"<#{link.text_channel_id}>")

    if not changed:
        return f"Every linked channel is already in {mode} mode."
    return f"Now in {mode} mode (sessions restarted, memory kept): " + ", ".join(changed) + "."


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


# -- bots -------------------------------------------------------------------

# What a MULCA bot needs in a channel: View Channel, Send Messages, Read
# Message History, Connect, Speak, Use Voice Activity.
BOT_PERMISSIONS = discord.Permissions(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    connect=True,
    speak=True,
    use_voice_activation=True,
)


@dataclass(frozen=True, slots=True)
class TokenProbe:
    """What a bot token belongs to, checked with Discord before saving it."""

    bot_id: int
    name: str
    application_id: int
    missing_intents: tuple[str, ...]
    public: bool


async def probe_token(token: str) -> TokenProbe:
    """Log in with `token` (no gateway connection) and read its app's setup."""

    client = discord.Client(intents=discord.Intents.none())
    try:
        await client.login(token)
        app = await client.application_info()
        flags = app.flags
        missing = []
        if not (flags.gateway_message_content or flags.gateway_message_content_limited):
            missing.append("Message Content Intent")
        if not (flags.gateway_guild_members or flags.gateway_guild_members_limited):
            missing.append("Server Members Intent")
        return TokenProbe(
            bot_id=client.user.id,
            name=client.user.name,
            application_id=app.id,
            missing_intents=tuple(missing),
            public=app.bot_public,
        )
    finally:
        await client.close()


async def set_model(
    manager: BotManager,
    model: str,
    target: str | None,
    guild_id: int,
    *,
    include_intervention: bool = False,
    admin_token: str | None = None,
    set_server: Callable[..., Awaitable[str | None]] = set_server_model,
) -> str:
    """
    /mulca model: the main agent's realtime model, and with
    `include_intervention` the intervention agent's too. For one bot it is
    saved here and sent on that bot's next sessions (which are restarted
    now); for every bot it is MUCA-Server's own setting, which ends every
    session so they reopen on it. A bot's own choice outranks the server's.
    """

    model = model.strip()
    if not model:
        return "Name a model."

    if target is None or target.strip().lower() == ALL:
        if not admin_token:
            return "MUCA_ADMIN_TOKEN isn't set, so MULCA can't change the server's model."
        problem = await set_server(
            manager.primary.registry.url,
            admin_token,
            model,
            include_intervention=include_intervention,
        )
        if problem:
            return f"MUCA-Server wouldn't change its model: {problem}."
        # Kept here too: MUCA-Server saves it, but /mulca status reads it here.
        manager.store.set_server_models(model, model if include_intervention else None)
        return (
            f"MUCA-Server now uses `{model}`; every session was restarted. "
            "A bot set on its own keeps its own model."
        )

    try:
        bots = manager.resolve(target, guild_id)
    except AmbiguousBotName as exc:
        return _ambiguous_bot_message(exc)

    if not bots:
        return f"No MULCA bot called {target!r} in this server."

    for bot in bots:
        manager.store.set_models(
            bot.user_id,
            model,
            model if include_intervention else None,
        )
        await bot.restart_all()

    names = ", ".join(f"**{bot.name}**" for bot in bots)
    return f"{names} now use `{model}`; their sessions were restarted."


# /mulca course's own choice besides the courses: forget the setting, so the
# server's name (or the default) decides again.
AUTO = "auto"


async def set_course(
    manager: BotManager,
    course: str | None,
    target: str | None,
    guild_id: int,
) -> str:
    """
    /mulca course: which course's material the MULCAs in this server teach.
    For every bot in it (the server's setting), or for one bot there (its
    own, outranking the server's). `auto` forgets the setting. Without a
    course, shows each bot's and why. A change restarts this server's
    sessions, so they reopen on it; other servers are untouched.
    """

    every_bot = target is None or target.strip().lower() == ALL
    try:
        bots = manager.in_guild(guild_id) if every_bot else manager.resolve(target, guild_id)
    except AmbiguousBotName as exc:
        return _ambiguous_bot_message(exc)

    if not bots:
        return (
            "No MULCA bot in this server."
            if every_bot
            else f"No MULCA bot called {target!r} in this server."
        )

    if course is not None:
        setting = None if course == AUTO else course
        if every_bot:
            manager.store.set_course(guild_id, setting)
        for bot in bots:
            if not every_bot:
                manager.store.set_course(guild_id, setting, bot.user_id)
            for link in bot.links():
                if link.guild_id == guild_id:
                    await bot.restart_link(link)

    lines = []
    for bot in bots:
        chosen, source = bot.course_choice(guild_id)
        lines.append(f"**{bot.name}**: {chosen.upper()} ({source})")
    if course is not None:
        lines.append("Their sessions in this server were restarted.")
    return "\n".join(lines)


async def set_cost_alert(
    manager: BotManager,
    *,
    webhook_url: str | None,
    threshold_usd: float | None,
    admin_token: str | None = None,
    set_server: Callable[..., Awaitable[str | None]] = set_server_cost_alert,
) -> str:
    """
    /mulca costalert: MUCA-Server's own cost-alert webhook/threshold --
    deployment-wide, like /mulca model, but unlike it nothing needs to
    restart since no live session depends on these.
    """

    if webhook_url is None and threshold_usd is None:
        return "Set a webhook, a threshold, or both."

    if not admin_token:
        return "MUCA_ADMIN_TOKEN isn't set, so MULCA can't change this."

    problem = await set_server(
        manager.primary.registry.url,
        admin_token,
        webhook_url=webhook_url,
        threshold_usd=threshold_usd,
    )
    if problem:
        return f"MUCA-Server wouldn't change its cost-alert settings: {problem}."

    changed = []
    if webhook_url is not None:
        changed.append("webhook")
    if threshold_usd is not None:
        changed.append(f"${threshold_usd:g} threshold")
    return f"MUCA-Server's cost alert {' and '.join(changed)} updated."


# Discord's attachment limit for a server without boosts is 10 MB.
EXPORT_MAX_PLAIN_BYTES = 9_000_000


@dataclass
class ExportResult:
    reply: str
    filename: str | None = None
    data: bytes | None = None


def _export_name(bot: BotRuntime, link: Link) -> str:
    name = bot._channel_name_for(link) or link.name
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


async def export_logs(
    manager: BotManager,
    guild_id: int,
    channel,
    *,
    all: bool = False,
    days: int = 1,
    admin_token: str | None = None,
    fetch: Callable[..., Awaitable[tuple[str | None, str | None]]] = fetch_episodic_export,
    now: float | None = None,
) -> ExportResult:
    """
    /mulca export: a linked channel's episodic log as CSV (or every linked
    channel's in this server, zipped), the last `days` days -- 0 for all of
    it. Zipped anyway when one CSV is too big to attach.
    """

    if not admin_token:
        return ExportResult("MUCA_ADMIN_TOKEN isn't set, so MULCA can't read the logs.")

    if all:
        targets = [
            (bot, link)
            for bot in manager.resolve(None, guild_id)
            for link in bot.links()
            if link.guild_id == guild_id
        ]
        if not targets:
            return ExportResult("No linked channel in this server.")
    else:
        if channel is None:
            return ExportResult("Pick a text channel, or run this in one.")
        found = manager.link_for_channel(channel.id)
        if found is None:
            return ExportResult(f"MULCA doesn't serve <#{channel.id}>.")
        targets = [found]

    since = None if days <= 0 else (now or time.time()) - days * 86_400
    stamp = datetime.fromtimestamp(now or time.time()).strftime("%Y%m%d-%H%M")

    files: dict[str, str] = {}
    failed = []
    for bot, link in targets:
        csv_text, problem = await fetch(
            manager.primary.registry.url,
            admin_token,
            link.conversation_id,
            since=since,
        )
        if csv_text is None:
            failed.append(f"<#{link.text_channel_id}> ({problem})")
        else:
            files[f"{_export_name(bot, link)}-{stamp}.csv"] = csv_text

    span = "everything" if since is None else f"the last {days} day(s)"
    lines = [f"Episodic log, {span}." if files else "Nothing to export."]
    if failed:
        lines.append("Could not export: " + ", ".join(failed) + ".")
    reply = "\n".join(lines)
    if not files:
        return ExportResult(reply)

    if not all:
        filename, text = next(iter(files.items()))
        data = text.encode("utf-8")
        if len(data) <= EXPORT_MAX_PLAIN_BYTES:
            return ExportResult(reply, filename, data)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, text in files.items():
            archive.writestr(filename, text)
    return ExportResult(reply, f"mulca-export-{stamp}.zip", buffer.getvalue())


def _usd(usd: float | None) -> str:
    return "no limit" if usd is None else f"${usd:.2f}"


def _limit_target(
    manager: BotManager,
    target: str | None,
    guild_id: int,
) -> tuple[str, str] | str:
    """The (store scope, label) a /mulca limit target means, or why none."""

    wanted = (target or ALL).strip().lower()
    if wanted == ALL:
        return EACH, "Every bot"
    if wanted == POOL:
        return POOL, "All bots together"

    try:
        bots = manager.resolve(target, guild_id)
    except AmbiguousBotName as exc:
        return _ambiguous_bot_message(exc)
    if not bots:
        return f"No MULCA bot called {target!r} in this server."
    return bot_scope(bots[0].user_id), f"**{bots[0].name}**"


async def set_limit(
    manager: BotManager,
    target: str | None,
    daily: float | None,
    weekly: float | None,
    monthly: float | None,
    guild_id: int,
) -> str:
    """/mulca limit set: USD per day, week and month; any left out stays."""

    if daily is None and weekly is None and monthly is None:
        return "Give a daily, weekly or monthly limit, in USD."

    found = _limit_target(manager, target, guild_id)
    if isinstance(found, str):
        return found
    scope, label = found

    meter = UsageMeter(manager.store)
    current = (
        meter.limits(None)["pool"]
        if scope == POOL
        else meter.limits(None if scope == EACH else int(scope.split(":")[1]))["bot"]
    )
    limits = tuple(
        old if new is None else max(0.0, new)
        for new, old in zip((daily, weekly, monthly), current)
    )
    manager.store.set_limit(scope, *limits)
    for bot in manager.bots:
        await bot.recheck_limits()

    reply = (
        f"{label}: {_usd(limits[0])} a day, {_usd(limits[1])} a week, "
        f"{_usd(limits[2])} a month."
    )
    if scope == EACH and manager.store.limit(POOL) is None:
        reply += (
            f" All bots together get {POOL_FACTOR}x that, until "
            "`/mulca limit set target:pool` sets it on its own."
        )
    return reply


async def clear_limit(manager: BotManager, target: str | None, guild_id: int) -> str:
    """/mulca limit clear."""

    found = _limit_target(manager, target, guild_id)
    if isinstance(found, str):
        return found
    scope, label = found

    manager.store.clear_limit(scope)
    for bot in manager.bots:
        await bot.recheck_limits()
    return f"{label}: back to the default limits."


STAGE_NAMES = ("normal", "warned", "listening only", "text only", "stopped")
PERIOD_NAMES = {"daily": "today", "weekly": "this week", "monthly": "this month"}


def format_usage(
    manager: BotManager,
    target: str | None,
    guild_id: int,
    *,
    details: bool = False,
) -> str:
    """/mulca usage: spending today, this week and this month, against the limits."""

    try:
        bots = manager.resolve(target, guild_id)
    except AmbiguousBotName as exc:
        return _ambiguous_bot_message(exc)
    if not bots:
        return f"No MULCA bot called {target!r} in this server."

    def line(label: str, budgets) -> str:
        spent = {b.kind: b for b in budgets}
        return f"{label}: " + " · ".join(
            f"{PERIOD_NAMES[kind]} ${spent[kind].used:.2f} of "
            f"${spent[kind].limit:.2f} ({spent[kind].share:.0%})"
            if kind in spent
            else f"{PERIOD_NAMES[kind]} no limit"
            for kind in KINDS
        )

    lines = []
    for bot in bots:
        budgets = bot.usage.budgets(bot.user_id)
        level, _ = bot.usage.stage(bot.user_id)
        lines.append(
            line(f"**{bot.name}**", [b for b in budgets if b.scope == "bot"])
            + f" -- now: {STAGE_NAMES[level]}"
        )
        if details:
            lines.extend(_cost_details(bot))

    lines.append(
        line(
            "All bots together",
            [b for b in bots[0].usage.budgets(bots[0].user_id) if b.scope == "pool"],
        )
    )
    return "\n".join(lines)


def _cost_details(bot: BotRuntime) -> list[str]:
    """What a bot's spending went on, by period and by what made the calls."""

    lines = []
    for kind, by_agent in bot.usage.details(bot.user_id).items():
        lines.append(f"  {PERIOD_NAMES[kind].capitalize()}:")
        if not by_agent:
            lines.append("    nothing yet")
        for agent, counts in by_agent.items():
            fresh_text, cached_text, fresh_audio, cached_audio, out_text, out_audio, usd = counts
            lines.append(
                f"    {agent}: text in {fresh_text:,} (+{cached_text:,} cached) · "
                f"audio in {fresh_audio:,} (+{cached_audio:,} cached) · "
                f"text out {out_text:,} · audio out {out_audio:,} · ${usd:.4f}"
            )
    return lines


def invite_url(application_id: int) -> str:
    return discord.utils.oauth_url(
        application_id,
        permissions=BOT_PERMISSIONS,
        scopes=("bot",),
    )


async def add_bot(
    manager: BotManager,
    token: str,
    *,
    added_by: int | None = None,
    probe: Callable[[str], Awaitable[TokenProbe]] = probe_token,
) -> str:
    """/mulca bot add: check the token, save it, start the bot."""

    token = token.strip()
    if token == manager.primary_token:
        return "That's the main MULCA bot's token: it's already running."

    try:
        info = await probe(token)
    except discord.LoginFailure:
        return (
            "Discord rejected that token. Copy it again: Developer Portal → "
            "your application → Bot → Reset Token."
        )
    except Exception as exc:
        logger.warning("Could not check a bot token: %s", type(exc).__name__)
        return "Couldn't check that token with Discord right now. Try again in a minute."

    running = manager.bot_by_id(info.bot_id)
    if running is not None:
        return f"**{info.name}** is already part of MULCA, and running."

    if info.missing_intents:
        return (
            f"**{info.name}** needs these turned on first, in the Developer "
            f"Portal (your application → Bot): {', '.join(info.missing_intents)}. "
            "Then run /mulca bot add again."
        )

    manager.store.add_bot(
        BotRecord(bot_id=info.bot_id, name=info.name, token=token),
        added_by=added_by,
    )
    state = await manager.start_bot(
        BotRecord(bot_id=info.bot_id, name=info.name, token=token),
    )

    lines = [
        f"Added **{info.name}** ({state}).",
        f"Invite it to a server: {invite_url(info.application_id)}",
        f"Then link channels to it: `/mulca link bot:{info.name}`.",
    ]
    if not info.public:
        lines.append(
            "Its application isn't public, so only its owner can use that invite "
            "link (or turn on Public Bot in the Developer Portal)."
        )
    return "\n".join(lines)


async def remove_bot(manager: BotManager, target: str, *, force: bool = False) -> str:
    """/mulca bot remove: stop an added bot and forget its token."""

    wanted = target.strip().lower()
    records = [
        record
        for record in manager.store.added_bots()
        if record.name.lower() == wanted or str(record.bot_id) == wanted
    ]
    if not records:
        if manager.primary.name.lower() == wanted or str(manager.primary.user_id) == wanted:
            return "The main MULCA bot can't be removed; its token is the stack's secret."
        return f"No added bot called {target!r}. `/mulca bot list` shows them."

    record = records[0]
    links = manager.store.links_for(record.bot_id)
    if links and not force:
        channels = ", ".join(f"<#{link.text_channel_id}>" for link in links)
        return (
            f"**{record.name}** still serves {channels}. Unlink them first, "
            "or run this again with `force: True` to unlink them for you."
        )

    runtime = manager.bot_by_id(record.bot_id)
    for link in links:
        if runtime is not None:
            await runtime.unlink(link)
        manager.store.remove(link.text_channel_id)

    await manager.stop_bot(record.bot_id)
    manager.store.remove_bot(record.bot_id)

    return (
        f"Removed **{record.name}**: stopped, and its token deleted. "
        "To also remove it from your Discord server, kick it there."
    )


def list_bots(manager: BotManager) -> str:
    """/mulca bot list: every bot of this deployment. Never their tokens."""

    primary = manager.primary
    lines = [
        f"**{primary.name}** (main, id {primary.user_id}): "
        + ("stopped" if primary.paused else "online")
        + f", {len(manager.store.links_for(primary.user_id))} link(s)"
    ]
    for record in manager.store.added_bots():
        runtime = manager.bot_by_id(record.bot_id)
        state = manager.states.get(record.bot_id, "not running")
        if runtime is not None and runtime.paused:
            state = "stopped"
        lines.append(
            f"**{record.name}** (id {record.bot_id}): {state}, "
            f"{len(manager.store.links_for(record.bot_id))} link(s)"
        )

    return "\n".join(lines)


# ----------------------------------------------------------------------
# Discord glue
# ----------------------------------------------------------------------


class AddBotModal(discord.ui.Modal, title="Add a MULCA bot"):
    """The token goes in a form, never in a message anyone else could see."""

    token = discord.ui.TextInput(
        label="Bot token",
        placeholder="Developer Portal → your application → Bot → Reset Token",
        style=discord.TextStyle.short,
        min_length=50,
        max_length=100,
    )

    def __init__(self, manager: BotManager) -> None:
        super().__init__()
        self._manager = manager

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await add_bot(
            self._manager,
            self.token.value,
            added_by=interaction.user.id,
        )
        await interaction.followup.send(reply, ephemeral=True)


# custom_id, not the view instance, is what Discord remembers across a
# restart -- registered once via add_view() below, so a button on a
# message posted days ago still reaches this same callback after a
# redeploy, with no per-message state to reconstruct.
LISTEN_BUTTON_CUSTOM_ID = "mulca:listen"


class ListenView(discord.ui.View):
    """
    "toggle" mode: the button form of /listen. Persistent (timeout=None,
    a fixed custom_id) so it keeps working on old messages after a restart --
    see install_commands' add_view() call.
    """

    def __init__(self, manager: BotManager) -> None:
        super().__init__(timeout=None)
        self._manager = manager

    @discord.ui.button(
        label="🎙️ Talk to MULCA",
        style=discord.ButtonStyle.primary,
        custom_id=LISTEN_BUTTON_CUSTOM_ID,
    )
    async def listen(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        found = self._manager.link_for_channel(interaction.channel_id)
        if found is None:
            await interaction.response.send_message(
                "MULCA doesn't run in this channel.",
                ephemeral=True,
            )
            return

        bot, link = found
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            now_listening = await bot.arm_listening(link, reply_channel=interaction.channel)
        except MucaConnectionLost:
            await interaction.followup.send(
                "Couldn't reach MULCA just now -- try again in a moment."
            )
            return

        await interaction.followup.send(
            listening_toggle_message(bot.name, now_listening)
        )


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

    # Registers the custom_id -> callback mapping only -- no Discord API
    # call, so this doesn't need to wait for on_ready, and it makes a
    # button on a message posted before a restart work again immediately.
    primary.client.add_view(ListenView(manager))

    async def bot_choices(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        bots = manager.in_guild(interaction.guild_id or 0)
        name_counts: dict[str, int] = {}
        for bot in bots:
            name_counts[bot.name] = name_counts.get(bot.name, 0) + 1

        choices = [app_commands.Choice(name=ALL, value=ALL)] + [
            # Two bots running from the same code share a name until one is
            # renamed -- submit the id instead of the ambiguous name so
            # picking from the list can never resolve to the wrong bot
            # (see AmbiguousBotName).
            app_commands.Choice(
                name=(
                    f"{bot.name} ({bot.user_id})"
                    if name_counts[bot.name] > 1
                    else bot.name
                ),
                value=str(bot.user_id) if name_counts[bot.name] > 1 else bot.name,
            )
            for bot in bots
        ]
        return [
            choice for choice in choices if current.lower() in choice.name.lower()
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
        reply = restart_message(interaction.user.mention, outcome)
        if bot.notices.is_active(LIMIT):
            # A restart never resets usage: the limit still holds.
            reply += " It's still over its usage limit, though."
        await interaction.followup.send(reply)

    # -- /listen ----------------------------------------------------------

    @tree.command(
        name="listen",
        description="\"toggle\" mode: MULCA starts listening for a bit.",
    )
    @app_commands.guild_only()
    async def listen(interaction: discord.Interaction) -> None:
        found = manager.link_for_channel(interaction.channel_id)
        if found is None:
            await interaction.response.send_message(
                "MULCA doesn't run in this channel.",
                ephemeral=True,
            )
            return

        bot, link = found
        await interaction.response.defer(thinking=True)
        try:
            now_listening = await bot.arm_listening(link, reply_channel=interaction.channel)
        except MucaConnectionLost:
            await interaction.followup.send(
                "Couldn't reach MULCA just now -- try again in a moment."
            )
            return

        await interaction.followup.send(
            listening_toggle_message(bot.name, now_listening)
        )

    # -- /help ------------------------------------------------------------

    @tree.command(
        name="help",
        description="What MULCA is and how to talk to it.",
    )
    async def help_command(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(HELP_MESSAGE, ephemeral=True)

    # -- /diary -----------------------------------------------------------

    @tree.command(
        name="diary",
        description="Link to the diary you fill in after every session.",
    )
    async def diary(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(DIARY_MESSAGE, ephemeral=True)

    # -- /mulca ... -----------------------------------------------------

    mulca = MulcaGroup(
        name="mulca",
        description="Control MULCA (needs Manage Server).",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @mulca.command(name="status", description="Show every MULCA bot in this server.")
    async def status(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        statuses = [
            bot.status(interaction.guild_id)
            for bot in manager.in_guild(interaction.guild_id)
        ]
        await send_long(
            interaction,
            format_status(statuses)
            + "\n\nSpending:\n"
            + format_usage(manager, None, interaction.guild_id),
        )

    @mulca.command(
        name="button",
        description="Post a \"toggle\"-mode listen button in this channel.",
    )
    async def button(interaction: discord.Interaction) -> None:
        found = manager.link_for_channel(interaction.channel_id)
        if found is None:
            await interaction.response.send_message(
                "MULCA doesn't run in this channel.",
                ephemeral=True,
            )
            return

        _, link = found
        await interaction.response.send_message(
            "Press to let MULCA listen for a bit (\"toggle\" mode only; "
            "does nothing in ambient or \"transcribe\" mode)."
            + (
                ""
                if link.listening_mode == "toggle"
                else " This channel isn't in \"toggle\" mode right now "
                "(`/mulca link mode:toggle`)."
            ),
            view=ListenView(manager),
        )

    @mulca.command(
        name="link",
        description="Make MULCA serve a text channel, and optionally a voice channel.",
    )
    @app_commands.describe(
        text="The text channel (default: this one). MULCA's memory belongs to it.",
        voice="A voice channel MULCA joins whenever someone is in it.",
        bot="Which MULCA bot (default: the main one).",
        transcripts="Also post what MULCA says out loud in the text channel.",
        dms="Let people who can see the text channel DM MULCA (default: unchanged, off for a new link).",
        # Discord shows at most 100 characters (discord.py cuts the rest
        # off). The other modes: toggle (/listen or the button opens a
        # window), transcribe ("MULCA start" opens a window hands-free).
        # Default: unchanged, the server's own for a new link.
        mode=(
            "wake: \"MULCA start\" brings MULCA in until it goes quiet. "
            "ambient: judges every turn."
        ),
    )
    @app_commands.autocomplete(bot=bot_choices)
    async def link(
        interaction: discord.Interaction,
        text: discord.TextChannel | None = None,
        voice: discord.VoiceChannel | None = None,
        bot: str | None = None,
        transcripts: bool = False,
        dms: bool | None = None,
        mode: Literal["ambient", "toggle", "transcribe", "wake", "wake_v2"] | None = None,
    ) -> None:
        text = text or interaction.channel
        if not isinstance(text, discord.TextChannel):
            await interaction.response.send_message(
                "Pick a text channel, or run this in one.",
                ephemeral=True,
            )
            return

        if bot is None or bot.strip().lower() == ALL:
            chosen = [manager.primary]
        else:
            try:
                chosen = manager.resolve(bot, interaction.guild_id)
            except AmbiguousBotName as exc:
                await interaction.response.send_message(
                    _ambiguous_bot_message(exc),
                    ephemeral=True,
                )
                return

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
            allow_dms=dms,
            listening_mode=mode,
            created_by=interaction.user.id,
        )
        await interaction.followup.send(reply, ephemeral=True)

    @mulca.command(
        name="announce",
        description="Re-post the welcome/guidelines message in a linked channel, or every one.",
    )
    @app_commands.describe(
        channel="The linked text channel (default: this one). Ignored if all is true.",
        all="Post in every text channel linked in this server instead of just one.",
    )
    async def announce(
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        all: bool = False,
    ) -> None:
        reply = (
            await announce_intro_everywhere(manager, interaction.guild_id)
            if all
            else await announce_intro(manager, channel or interaction.channel)
        )
        await interaction.response.send_message(reply, ephemeral=True)

    @mulca.command(
        name="help",
        description="Post the help message in a linked channel, or every one (not ephemeral).",
    )
    @app_commands.describe(
        channel="The linked text channel (default: this one). Ignored if all is true.",
        all="Post in every text channel linked in this server instead of just one.",
    )
    async def mulca_help(
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        all: bool = False,
    ) -> None:
        reply = (
            await post_help_everywhere(manager, interaction.guild_id)
            if all
            else await post_help(manager, channel or interaction.channel)
        )
        await interaction.response.send_message(reply, ephemeral=True)

    @mulca.command(
        name="voiceupdate",
        description="Post how to start/stop MULCA in voice, in a linked channel or every one.",
    )
    @app_commands.describe(
        channel="The linked text channel (default: this one). Ignored if all is true.",
        all="Post in every text channel linked in this server instead of just one.",
    )
    async def voice_update(
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        all: bool = False,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = (
            await post_voice_update_everywhere(manager, interaction.guild_id)
            if all
            else await post_voice_update(manager, channel or interaction.channel)
        )
        await interaction.followup.send(reply, ephemeral=True)

    @mulca.command(
        name="greet",
        description="Post the first-session reminder in a linked channel, or every one.",
    )
    @app_commands.describe(
        channel="The linked text channel (default: this one). Ignored if all is true.",
        all="Post in every text channel linked in this server instead of just one.",
    )
    async def greet(
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        all: bool = False,
    ) -> None:
        reply = (
            await greet_first_session_everywhere(manager, interaction.guild_id)
            if all
            else await greet_first_session(manager, channel or interaction.channel)
        )
        await interaction.response.send_message(reply, ephemeral=True)

    @mulca.command(
        name="dms",
        description="Let the people of a linked channel DM MULCA, or stop them (off by default).",
    )
    @app_commands.describe(
        enabled="True: people who can see the channel may DM MULCA. False: they can't.",
        channel="The linked text or voice channel (default: this one).",
    )
    async def dms(
        interaction: discord.Interaction,
        enabled: bool,
        channel: discord.TextChannel | discord.VoiceChannel | None = None,
    ) -> None:
        channel_id = channel.id if channel is not None else interaction.channel_id
        reply = await set_dms(manager, channel_id, enabled)
        await interaction.response.send_message(reply, ephemeral=True)

    @mulca.command(
        name="mode",
        description="Switch every linked channel (or one bot's) to a listening mode, no relink needed.",
    )
    @app_commands.describe(
        mode="ambient, toggle, transcribe, wake or wake_v2 (see /mulca link).",
        bot="One bot (default: every bot in this server).",
    )
    @app_commands.autocomplete(bot=bot_choices)
    async def mode_command(
        interaction: discord.Interaction,
        mode: Literal["ambient", "toggle", "transcribe", "wake", "wake_v2"],
        bot: str | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await set_mode(manager, mode, bot, interaction.guild_id)
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
        await send_long(interaction, reply)

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

    @mulca.command(name="model", description="Change the realtime model of every MULCA, or of one bot.")
    @app_commands.describe(
        model="The OpenAI realtime model, e.g. gpt-realtime.",
        bot="One bot (default: every bot).",
        include_intervention="Also change the intervention agent's model, not only the main one.",
    )
    @app_commands.autocomplete(bot=bot_choices)
    async def model_command(
        interaction: discord.Interaction,
        model: str,
        bot: str | None = None,
        include_intervention: bool = False,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await set_model(
            manager,
            model,
            bot,
            interaction.guild_id,
            include_intervention=include_intervention,
            admin_token=os.environ.get("MUCA_ADMIN_TOKEN"),
        )
        await interaction.followup.send(reply, ephemeral=True)

    @mulca.command(
        name="course",
        description="Which course MULCA teaches in this server (by default, the one the server's name names).",
    )
    @app_commands.describe(
        course="The course, or auto to go by the server's name again (leave empty to just see it).",
        bot="One bot (default: every bot in this server).",
    )
    @app_commands.choices(
        course=[
            app_commands.Choice(name=name.upper() if name != AUTO else name, value=name)
            for name in (*courses.COURSES, AUTO)
        ]
    )
    @app_commands.autocomplete(bot=bot_choices)
    async def course_command(
        interaction: discord.Interaction,
        course: str | None = None,
        bot: str | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await set_course(manager, course, bot, interaction.guild_id)
        await interaction.followup.send(reply, ephemeral=True)

    @mulca.command(
        name="costalert",
        description="Set MUCA-Server's cost-alert Discord webhook and/or $ threshold step.",
    )
    @app_commands.describe(
        webhook="A Discord channel webhook URL to post spend alerts to.",
        threshold_usd="Post an alert every time total spend crosses another this-many dollars (e.g. 1, or 0.01).",
    )
    async def cost_alert_command(
        interaction: discord.Interaction,
        webhook: str | None = None,
        threshold_usd: float | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await set_cost_alert(
            manager,
            webhook_url=webhook,
            threshold_usd=threshold_usd,
            admin_token=os.environ.get("MUCA_ADMIN_TOKEN"),
        )
        await interaction.followup.send(reply, ephemeral=True)

    @mulca.command(
        name="export",
        description="Download a linked channel's log (messages, spoken turns, wake/call events) as CSV.",
    )
    @app_commands.describe(
        channel="The linked text channel (default: this one). Ignored if all is true.",
        all="Every text channel linked in this server, zipped.",
        days="How many days back (default 1; 0 for everything).",
    )
    async def export_command(
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        all: bool = False,
        days: int = 1,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        result = await export_logs(
            manager,
            interaction.guild_id,
            channel or interaction.channel,
            all=all,
            days=days,
            admin_token=os.environ.get("MUCA_ADMIN_TOKEN"),
        )
        if result.data is None:
            await interaction.followup.send(result.reply, ephemeral=True)
            return
        await interaction.followup.send(
            result.reply,
            file=discord.File(io.BytesIO(result.data), filename=result.filename),
            ephemeral=True,
        )

    # -- /mulca bot ... --------------------------------------------------

    bots = app_commands.Group(
        name="bot",
        description="MULCA's bot accounts (for the whole deployment).",
        parent=mulca,
    )

    async def added_bot_choices(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=record.name, value=str(record.bot_id))
            for record in manager.store.added_bots()
            if current.lower() in record.name.lower()
        ][:25]

    @bots.command(name="add", description="Add another bot account (its token goes in a private form).")
    async def bot_add(interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddBotModal(manager))

    @bots.command(name="remove", description="Stop an added bot and delete its token.")
    @app_commands.describe(
        bot="The added bot.",
        force="Also unlink the channels it still serves.",
    )
    @app_commands.autocomplete(bot=added_bot_choices)
    async def bot_remove(
        interaction: discord.Interaction,
        bot: str,
        force: bool = False,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await remove_bot(manager, bot, force=force)
        await interaction.followup.send(reply, ephemeral=True)

    @bots.command(name="list", description="Every MULCA bot account, and what it's doing.")
    async def bot_list(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        await send_long(interaction, list_bots(manager))

    # -- /mulca limit ..., /mulca usage ----------------------------------

    limit = app_commands.Group(
        name="limit",
        description="USD MULCA may spend per day, week and month (whole deployment).",
        parent=mulca,
    )

    async def limit_choices(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        pool = app_commands.Choice(name=f"{POOL} (all bots together)", value=POOL)
        choices = await bot_choices(interaction, current)
        return ([pool] if current.lower() in pool.name else []) + choices[:24]

    @limit.command(name="set", description="Limit how much MULCA may spend per day, week and month.")
    @app_commands.describe(
        target="One bot, all (each bot, by default), or pool (all bots together).",
        daily="USD per day, e.g. 30. Left out: unchanged.",
        weekly="USD per week, e.g. 50. Left out: unchanged.",
        monthly="USD per month, e.g. 100. Left out: unchanged.",
    )
    @app_commands.autocomplete(target=limit_choices)
    async def limit_set(
        interaction: discord.Interaction,
        target: str,
        daily: float | None = None,
        weekly: float | None = None,
        monthly: float | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await set_limit(
            manager, target, daily, weekly, monthly, interaction.guild_id
        )
        await interaction.followup.send(reply, ephemeral=True)

    @limit.command(name="clear", description="Back to the default usage limits.")
    @app_commands.describe(target="One bot, all (each bot), or pool (all bots together).")
    @app_commands.autocomplete(target=limit_choices)
    async def limit_clear(interaction: discord.Interaction, target: str) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        reply = await clear_limit(manager, target, interaction.guild_id)
        await interaction.followup.send(reply, ephemeral=True)

    @mulca.command(name="usage", description="What MULCA spent today, this week and this month.")
    @app_commands.describe(
        bot="One bot, or all of them in this server (default).",
        details="Also each agent's tokens and cost (main, observer, transcription...).",
    )
    @app_commands.autocomplete(bot=bot_choices)
    async def usage_command(
        interaction: discord.Interaction,
        bot: str | None = None,
        details: bool = False,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        await send_long(
            interaction,
            format_usage(manager, bot, interaction.guild_id, details=details),
        )

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
