"""
One Discord bot account at work (BotRuntime), and the bots of this process
(BotManager) -- what the Discord event handlers and the slash commands act
on.

A BotRuntime is one discord.Client, its MUCA-Server sessions (one per
scope), the instance it serves and its voice channel. It can be paused
(/mulca stop: out of voice, sessions closed, every event ignored, but still
logged in so commands keep working) and its sessions restarted (/restart:
fresh provider connections on MUCA-Server, the same memory).
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import discord

from .instances import (
    MulcaInstance,
    first_available_instance,
    instance_for_channel,
    instance_for_participant,
)
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
    name: str
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
    instance: MulcaInstance
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
    # Every configured instance; `active` is the one this bot runs as.
    instances: list[MulcaInstance]
    is_primary: bool = True

    active: list[MulcaInstance] = field(default_factory=list)
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

    def link_for_channel(self, channel_id: int) -> MulcaInstance | None:
        return instance_for_channel(self.active, channel_id)

    def roster(self, instance: MulcaInstance) -> dict[int, str]:
        """Everyone in the instance's text channel or its voice channel."""

        roster: dict[int, str] = {}
        for channel_id in (instance.text_channel_id, instance.voice_channel_id):
            channel = self.client.get_channel(channel_id) if channel_id else None
            for member in _humans(channel):
                roster[member.id] = member.display_name

        return roster

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------

    async def join_voice(self, instance: MulcaInstance) -> None:
        from discord.ext import voice_recv

        from .voice import VoiceBridge

        if instance.name in self.voice:
            return

        channel = self.client.get_channel(instance.voice_channel_id)
        if channel is None:
            logger.warning(
                "Voice channel %s of %s not found",
                instance.voice_channel_id,
                instance.name,
            )
            return

        logger.info("Joining voice channel %s for %s", channel, instance.name)
        voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)

        bridge = VoiceBridge(
            scope=Scope(conversation_id=instance.conversation_id),
            registry=self.registry,
            voice_client=voice_client,
            reply_channel=self.client.get_channel(instance.text_channel_id),
            post_voice_transcripts=instance.post_voice_transcripts,
            roster=lambda: self.roster(instance),
        )
        self.voice[instance.name] = bridge
        await bridge.start()

    async def leave_voice(self, instance: MulcaInstance) -> None:
        bridge = self.voice.pop(instance.name, None)
        if bridge is None:
            return

        logger.info("Leaving the voice channel of %s", instance.name)
        await bridge.disconnect()

    async def sync_voice(self, instance: MulcaInstance) -> None:
        channel = self.client.get_channel(instance.voice_channel_id)
        if _humans(channel) and not self.paused:
            await self.join_voice(instance)
        else:
            await self.leave_voice(instance)

    async def _sync_all_voice(self) -> None:
        for instance in self.active:
            if instance.voice_channel_id is None:
                continue
            try:
                await self.sync_voice(instance)
            except Exception:
                logger.exception("Could not join voice for %s", instance.name)

    # ------------------------------------------------------------------
    # Control: /restart, /mulca stop|start|restart
    # ------------------------------------------------------------------

    async def restart_link(self, instance: MulcaInstance) -> RestartOutcome:
        """
        Restart one instance's MUCA-Server session: the server reconnects
        its provider (OpenAI) from scratch and reloads the saved memory.
        In voice, the bridge reopens it right away, roster included.
        """

        confirmed = await self.registry.restart(instance.conversation_id)

        bridge = self.voice.get(instance.name)
        if bridge is not None:
            await bridge.update_participants()

        return RestartOutcome(instance=instance, confirmed=confirmed)

    async def restart_all(self) -> list[RestartOutcome]:
        """Every instance's session, and every DM session, restarted."""

        outcomes = [await self.restart_link(instance) for instance in self.active]

        linked = {instance.conversation_id for instance in self.active}
        for conversation_id in list(self.registry.sessions):
            if conversation_id not in linked:
                await self.registry.restart(conversation_id)

        return outcomes

    async def pause(self) -> None:
        """Out of voice, every session closed, every event ignored."""

        if self.paused:
            return

        self.paused = True
        logger.info("Pausing %s", self.name)

        for instance in self.active:
            await self.leave_voice(instance)

        for conversation_id in list(self.registry.sessions):
            await self.registry.close(conversation_id, wait=RESTART_WAIT_SECONDS)

    async def resume(self) -> None:
        if not self.paused:
            return

        self.paused = False
        logger.info("Resuming %s", self.name)
        await self._sync_all_voice()

    def status(self) -> BotStatus:
        now = time.monotonic()
        links = []

        for instance in self.active:
            session = self.registry.find(instance.conversation_id)
            client = session.client if session is not None else None
            bridge = self.voice.get(instance.name)

            problems: list[str] = []
            for channel_id, voice in (
                (instance.text_channel_id, False),
                (instance.voice_channel_id, True),
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
                        f"missing {name} in {channel}"
                        for name in missing_permissions(channel, guild.me, voice=voice)
                    )

            links.append(
                LinkStatus(
                    name=instance.name,
                    text_channel_id=instance.text_channel_id,
                    voice_channel_id=instance.voice_channel_id,
                    in_voice=bridge is not None,
                    session_open=client is not None and client.is_open,
                    session_age_seconds=(
                        now - session.opened_at
                        if session is not None and client.is_open
                        else None
                    ),
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

        chosen = first_available_instance(
            self.instances,
            lambda channel_id: self.client.get_channel(channel_id) is not None,
        )

        # on_ready fires again after a full reconnect; if the choice changed
        # (e.g. the bot lost access to a channel), leave the old voice channel.
        for previous in self.active:
            if previous != chosen:
                await self.leave_voice(previous)
        self.active[:] = [chosen] if chosen is not None else []

        for instance in self.instances:
            if instance is chosen:
                continue
            visible = self.client.get_channel(instance.text_channel_id) is not None
            logger.info(
                "Not running as %s: %s",
                instance.name,
                "an earlier instance comes first"
                if visible
                else f"text channel {instance.text_channel_id} not visible",
            )

        if chosen is None:
            logger.warning(
                "None of the %d configured instances' text channels is "
                "visible to this bot; only DMs will be answered",
                len(self.instances),
            )
        else:
            logger.info(
                "Running as instance %s (text channel %s, voice channel %s)",
                chosen.name,
                chosen.text_channel_id,
                chosen.voice_channel_id,
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

        for instance in self.active:
            if instance.voice_channel_id not in touched:
                continue

            try:
                await self.sync_voice(instance)
            except Exception:
                logger.exception("Could not update voice for %s", instance.name)
                continue

            bridge = self.voice.get(instance.name)
            if bridge is None:
                continue

            if (
                before.channel is not None
                and before.channel.id == instance.voice_channel_id
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
        instance: MulcaInstance | None = None

        if is_dm:
            # Answering is permissive by design (BLUEPRINT.md: "open to DMs
            # from any individual user") -- participant_ids doesn't gate
            # that. It does gate one-way read access to a group's memory:
            # a recognized participant's DM gets it, a stranger's doesn't.
            linked_instance = instance_for_participant(
                self.active, message.author.id
            )
            scope = Scope(
                conversation_id=f"dm:{message.author.id}",
                is_dm=True,
                linked_conversation_id=(
                    linked_instance.conversation_id
                    if linked_instance is not None
                    else None
                ),
            )
        else:
            instance = self.link_for_channel(message.channel.id)
            if instance is None:
                # Not a channel the active MulcaInstance owns.
                return
            scope = Scope(conversation_id=instance.conversation_id)

        roster = self.roster(instance) if instance is not None else {}
        if instance is not None and not roster:
            roster = await _roster(message.channel)

        async def send(muca_client) -> None:
            if instance is not None:
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
                    instance.post_voice_transcripts if instance else False
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

    def link_for_channel(
        self,
        channel_id: int,
    ) -> tuple[BotRuntime, MulcaInstance] | None:
        for bot in self.bots:
            instance = bot.link_for_channel(channel_id)
            if instance is not None:
                return bot, instance

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
