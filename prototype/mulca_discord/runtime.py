"""
One Discord bot account at work (BotRuntime), and the bots of this process
(BotManager) -- what the Discord event handlers and the slash commands act
on.

A BotRuntime is one discord.Client, its MUCA-Server sessions (one per
scope), and the channels linked to it (links.py: /mulca link). It can be
paused (/mulca stop: out of voice, sessions closed, every event ignored, but
still logged in so commands keep working) and its sessions restarted
(/restart: fresh provider connections on MUCA-Server, the same memory).
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import discord

from .links import Link, LinkStore, link_for_channel
from .permissions import missing_permissions
from .sessions import RESTART_WAIT_SECONDS, Scope, SessionRegistry

logger = logging.getLogger(__name__)

ReadyHook = Callable[["BotRuntime"], Awaitable[None]]


async def _roster(channel: discord.abc.Messageable) -> dict[int, str]:
    members = getattr(channel, "members", [])
    return {member.id: member.display_name for member in members if not member.bot}


def _humans(channel) -> list:
    return [
        member
        for member in getattr(channel, "members", [])
        if not member.bot
    ]


# ----------------------------------------------------------------------
# Status, as plain data: the commands render it, tests read it.
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LinkStatus:
    text_channel_id: int
    voice_channel_id: int | None
    in_voice: bool
    session_open: bool
    session_age_seconds: float | None
    last_close_code: int | None
    problems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BotStatus:
    name: str
    online: bool
    latency_ms: float | None
    paused: bool
    uptime_seconds: float | None
    links: tuple[LinkStatus, ...]
    dm_sessions: int


@dataclass(frozen=True, slots=True)
class RestartOutcome:
    link: Link
    # Whether MUCA-Server confirmed it saved the conversation before the
    # session was reopened (False: it didn't answer in time).
    confirmed: bool


# ----------------------------------------------------------------------
# One bot
# ----------------------------------------------------------------------


@dataclass(eq=False)
class BotRuntime:
    client: discord.Client
    registry: SessionRegistry
    store: LinkStore
    is_primary: bool = True

    voice: dict[str, object] = field(default_factory=dict)
    paused: bool = False
    ready_at: float | None = None

    # Called after each on_ready, e.g. to sync slash commands.
    after_ready: list[ReadyHook] = field(default_factory=list)

    def install(self) -> None:
        """Route this client's Discord events here."""

        self.client.event(self.on_ready)
        self.client.event(self.on_voice_state_update)
        self.client.event(self.on_message)

    @property
    def name(self) -> str:
        user = self.client.user
        return user.name if user is not None else "MULCA"

    @property
    def user_id(self) -> int | None:
        user = self.client.user
        return user.id if user is not None else None

    def links(self) -> list[Link]:
        """The channels this bot serves, live from the store."""

        return self.store.links_for(self.user_id)

    def link_for_channel(self, channel_id: int) -> Link | None:
        return link_for_channel(self.links(), channel_id)

    def roster(self, link: Link) -> dict[int, str]:
        """Everyone in the link's text channel or its voice channel."""

        roster: dict[int, str] = {}
        for channel_id in (link.text_channel_id, link.voice_channel_id):
            channel = self.client.get_channel(channel_id) if channel_id else None
            for member in _humans(channel):
                roster[member.id] = member.display_name

        return roster

    def dm_link(self, user_id: int) -> Link | None:
        """
        The group memory a DM from this user may read: the linked channel
        they last spoke in, as long as they can still see it.
        """

        link = self.store.last_link_for(user_id)
        if link is None:
            return None

        channel = self.client.get_channel(link.text_channel_id)
        guild = getattr(channel, "guild", None)
        member = guild.get_member(user_id) if guild is not None else None
        if member is None or not channel.permissions_for(member).view_channel:
            return None

        return link

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------

    async def join_voice(self, link: Link) -> None:
        from discord.ext import voice_recv

        from .voice import VoiceBridge

        if link.name in self.voice:
            return

        channel = self.client.get_channel(link.voice_channel_id)
        if channel is None:
            logger.warning(
                "Voice channel %s of %s not found",
                link.voice_channel_id,
                link.name,
            )
            return

        logger.info("Joining voice channel %s for %s", channel, link.name)
        voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)

        bridge = VoiceBridge(
            scope=Scope(conversation_id=link.conversation_id),
            registry=self.registry,
            voice_client=voice_client,
            reply_channel=self.client.get_channel(link.text_channel_id),
            post_voice_transcripts=link.post_voice_transcripts,
            roster=lambda: self.roster(link),
        )
        self.voice[link.name] = bridge
        await bridge.start()

    async def leave_voice(self, link: Link) -> None:
        bridge = self.voice.pop(link.name, None)
        if bridge is None:
            return

        logger.info("Leaving the voice channel of %s", link.name)
        await bridge.disconnect()

    async def sync_voice(self, link: Link) -> None:
        channel = (
            self.client.get_channel(link.voice_channel_id)
            if link.voice_channel_id is not None
            else None
        )
        if _humans(channel) and not self.paused:
            await self.join_voice(link)
        else:
            await self.leave_voice(link)

    async def _sync_all_voice(self) -> None:
        for link in self.links():
            try:
                await self.sync_voice(link)
            except Exception:
                logger.exception("Could not join voice for %s", link.name)

    # ------------------------------------------------------------------
    # Linking: /mulca link|unlink
    # ------------------------------------------------------------------

    async def apply_link(self, link: Link, previous: Link | None) -> None:
        """
        Put a just-saved link into effect: a changed voice channel or
        transcript setting starts a new voice bridge.
        """

        if previous is not None and previous != link:
            await self.leave_voice(previous)

        if link.voice_channel_id is not None:
            await self.sync_voice(link)

    async def unlink(self, link: Link) -> None:
        """Out of its voice channel, its session closed (memory saved)."""

        await self.leave_voice(link)
        await self.registry.close(link.conversation_id, wait=RESTART_WAIT_SECONDS)

    # ------------------------------------------------------------------
    # Control: /restart, /mulca stop|start|restart
    # ------------------------------------------------------------------

    async def restart_link(self, link: Link) -> RestartOutcome:
        """
        Restart one link's MUCA-Server session: the server reconnects its
        provider (OpenAI) from scratch and reloads the saved memory. In
        voice, the bridge reopens it right away, roster included.
        """

        confirmed = await self.registry.restart(link.conversation_id)

        bridge = self.voice.get(link.name)
        if bridge is not None:
            await bridge.update_participants()

        return RestartOutcome(link=link, confirmed=confirmed)

    async def restart_all(self) -> list[RestartOutcome]:
        """Every link's session, and every DM session, restarted."""

        links = self.links()
        outcomes = [await self.restart_link(link) for link in links]

        linked = {link.conversation_id for link in links}
        for conversation_id in list(self.registry.sessions):
            if conversation_id not in linked:
                await self.registry.restart(conversation_id)

        return outcomes

    async def pause(self) -> None:
        """Out of voice, every session closed, every event ignored."""

        if self.user_id is not None:
            self.store.set_paused(self.user_id, True)

        if self.paused:
            return

        self.paused = True
        logger.info("Pausing %s", self.name)

        for link in self.links():
            await self.leave_voice(link)

        for conversation_id in list(self.registry.sessions):
            await self.registry.close(conversation_id, wait=RESTART_WAIT_SECONDS)

    async def resume(self) -> None:
        if self.user_id is not None:
            self.store.set_paused(self.user_id, False)

        if not self.paused:
            return

        self.paused = False
        logger.info("Resuming %s", self.name)
        await self._sync_all_voice()

    def status(self, guild_id: int | None = None) -> BotStatus:
        """This bot's state; its links in `guild_id` only, if given."""

        now = time.monotonic()
        links = []

        for link in self.links():
            if guild_id is not None and link.guild_id != guild_id:
                continue

            session = self.registry.find(link.conversation_id)
            client = session.client if session is not None else None
            is_open = client is not None and client.is_open

            problems: list[str] = []
            for channel_id, voice in (
                (link.text_channel_id, False),
                (link.voice_channel_id, True),
            ):
                if channel_id is None:
                    continue
                channel = self.client.get_channel(channel_id)
                if channel is None:
                    problems.append(f"can't see channel {channel_id}")
                    continue
                guild = getattr(channel, "guild", None)
                if guild is not None and guild.me is not None:
                    problems.extend(
                        f"missing {name} in <#{channel_id}>"
                        for name in missing_permissions(channel, guild.me, voice=voice)
                    )

            links.append(
                LinkStatus(
                    text_channel_id=link.text_channel_id,
                    voice_channel_id=link.voice_channel_id,
                    in_voice=link.name in self.voice,
                    session_open=is_open,
                    session_age_seconds=now - session.opened_at if is_open else None,
                    last_close_code=getattr(client, "close_code", None),
                    problems=tuple(problems),
                )
            )

        dm_sessions = sum(
            1
            for conversation_id, session in self.registry.sessions.items()
            if conversation_id.startswith("dm:") and session.client.is_open
        )

        latency = self.client.latency
        return BotStatus(
            name=self.name,
            online=self.client.is_ready(),
            latency_ms=latency * 1000 if math.isfinite(latency) else None,
            paused=self.paused,
            uptime_seconds=now - self.ready_at if self.ready_at is not None else None,
            links=tuple(links),
            dm_sessions=dm_sessions,
        )

    # ------------------------------------------------------------------
    # Discord events
    # ------------------------------------------------------------------

    async def on_ready(self) -> None:
        logger.info(
            "MULCA bot logged in as %s (id=%s)",
            self.client.user,
            self.user_id,
        )
        self.ready_at = time.monotonic()

        self.store.register_bot(self.user_id, self.name, is_primary=self.is_primary)
        self.paused = self.store.is_paused(self.user_id)
        if self.paused:
            logger.info("%s is stopped (/mulca stop); /mulca start resumes it", self.name)

        links = self.links()
        if not links:
            logger.warning(
                "No channel is linked to %s yet: use /mulca link in Discord. "
                "Only DMs will be answered until then.",
                self.name,
            )
        for link in links:
            visible = self.client.get_channel(link.text_channel_id) is not None
            logger.info(
                "Serving %s (text channel %s, voice channel %s)%s",
                link.name,
                link.text_channel_id,
                link.voice_channel_id,
                "" if visible else " -- but that text channel isn't visible",
            )

        await self._sync_all_voice()

        for hook in self.after_ready:
            try:
                await hook(self)
            except Exception:
                logger.exception("An on_ready hook failed")

    async def on_voice_state_update(self, member, before, after) -> None:
        if member.bot or self.paused:
            return

        touched = {
            channel.id
            for channel in (before.channel, after.channel)
            if channel is not None
        }

        for link in self.links():
            if link.voice_channel_id not in touched:
                continue

            if after.channel is not None and after.channel.id == link.voice_channel_id:
                # Joining a linked voice channel counts as taking part there.
                self.store.remember_speaker(member.id, link.text_channel_id)

            try:
                await self.sync_voice(link)
            except Exception:
                logger.exception("Could not update voice for %s", link.name)
                continue

            bridge = self.voice.get(link.name)
            if bridge is None:
                continue

            if (
                before.channel is not None
                and before.channel.id == link.voice_channel_id
                and (after.channel is None or after.channel.id != before.channel.id)
            ):
                bridge.forget(member.id)

            await bridge.update_participants()

    async def on_message(self, message: discord.Message) -> None:
        logger.debug(
            "on_message: author_id=%s is_bot=%s channel_id=%s content=%r",
            message.author.id,
            message.author.bot,
            message.channel.id,
            message.content,
        )

        if self.paused or message.author.bot or not message.content:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        link: Link | None = None

        if is_dm:
            # Answering is permissive by design (BLUEPRINT.md: "open to DMs
            # from any individual user"). What a DM may also read is the
            # group memory of the linked channel its sender last spoke in,
            # as long as they can still see it.
            linked = self.dm_link(message.author.id)
            scope = Scope(
                conversation_id=f"dm:{message.author.id}",
                is_dm=True,
                linked_conversation_id=(
                    linked.conversation_id if linked is not None else None
                ),
            )
        else:
            link = self.link_for_channel(message.channel.id)
            if link is None:
                # Not a channel linked to this bot.
                return
            scope = Scope(conversation_id=link.conversation_id)
            self.store.remember_speaker(message.author.id, link.text_channel_id)

        roster = self.roster(link) if link is not None else {}
        if link is not None and not roster:
            roster = await _roster(message.channel)

        async def send(muca_client) -> None:
            if link is not None:
                await muca_client.send_participants(roster)

            await muca_client.send_user_text(
                speaker=message.author.id,
                speaker_name=message.author.display_name,
                text=message.content,
            )

        try:
            await self.registry.run(
                scope,
                send,
                reply_channel=message.channel,
                post_voice_transcripts=(
                    link.post_voice_transcripts if link else False
                ),
                # A text message triggers a real cognitive turn -- unlike
                # voice's continuous frames, resending it on a reconnect
                # risks two independent replies to the same message (see
                # SessionRegistry.run's docstring). Drop it instead; the
                # next message reopens the session normally.
                retry_once=False,
            )
        except ConnectionError:
            logger.exception(
                "MUCA-Server is unreachable; dropping a message for %s",
                scope.conversation_id,
            )

    async def close(self) -> None:
        for bridge in list(self.voice.values()):
            await bridge.disconnect()
        self.voice.clear()

        await self.registry.close_all()


# ----------------------------------------------------------------------
# The bots of this process
# ----------------------------------------------------------------------


class BotManager:
    """
    The bots this process runs. One today; several later, all controlled
    through the primary bot's slash commands.
    """

    def __init__(self, bots: list[BotRuntime]) -> None:
        if not bots:
            raise ValueError("a BotManager needs at least one bot")
        self.bots = bots

    @property
    def primary(self) -> BotRuntime:
        return next((bot for bot in self.bots if bot.is_primary), self.bots[0])

    def bot_by_id(self, bot_id: int) -> BotRuntime | None:
        return next((bot for bot in self.bots if bot.user_id == bot_id), None)

    def link_for_channel(self, channel_id: int) -> tuple[BotRuntime, Link] | None:
        for bot in self.bots:
            link = bot.link_for_channel(channel_id)
            if link is not None:
                return bot, link

        return None

    def in_guild(self, guild_id: int) -> list[BotRuntime]:
        """The bots that are members of this Discord server."""

        return [
            bot
            for bot in self.bots
            if bot.client.get_guild(guild_id) is not None
        ]

    def resolve(self, target: str | None, guild_id: int) -> list[BotRuntime]:
        """
        "all" (or nothing) means every bot in this server; anything else is
        one bot's name or id. Never a bot outside this server.
        """

        bots = self.in_guild(guild_id)
        if target is None or target.strip().lower() in ("", "all"):
            return bots

        wanted = target.strip().lower()
        return [
            bot
            for bot in bots
            if bot.name.lower() == wanted or str(bot.user_id) == wanted
        ]
