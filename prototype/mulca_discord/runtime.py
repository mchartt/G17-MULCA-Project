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

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field

import discord

from . import messages
from .links import BotRecord, Link, LinkStore, link_for_channel
from .messages import Notices
from .permissions import missing_permissions
from .sessions import RESTART_WAIT_SECONDS, Scope, ScopeSession, SessionRegistry
from .usage import WARNING_MINUTES, UsageMeter

logger = logging.getLogger(__name__)

ReadyHook = Callable[["BotRuntime"], Awaitable[None]]


class AmbiguousBotName(Exception):
    """More than one bot in this server shares the name a command targeted."""

    def __init__(self, name: str, matches: list["BotRuntime"]) -> None:
        self.name = name
        self.matches = matches
        super().__init__(
            f"{len(matches)} bots in this server are named {name!r}"
        )

# The answer to a DM the bot doesn't take.
DMS_OFF_REPLY = messages.DMS_OFF

# The problems a bot tells its users about (messages.Notices), besides one
# "voice:<link>" per voice channel it can't join.
LIMIT = "limit"
WARNING = "warning"
OFFLINE = "offline"
PAUSED = "paused"
TURN_FAILED = "turn_failed"

# How often a bot over its limit checks whether it may answer again.
LIMIT_CHECK_SECONDS = 60.0


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
    allow_dms: bool
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
    # (main, intervention), each with where it comes from.
    models: tuple[str, str] = ("server default", "server default")


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

    usage: UsageMeter | None = None
    notices: Notices = field(default_factory=Notices)
    _tasks: set[asyncio.Task[None]] = field(default_factory=set, repr=False)
    _watch: asyncio.Task[None] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.usage is None:
            self.usage = UsageMeter(self.store)
        self.registry.on_reply = self._on_reply
        self.registry.on_server_error = self._on_server_error

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

    def roster_text(self, link: Link) -> dict[int, str]:
        """Everyone in the link's text channel."""

        channel = self.client.get_channel(link.text_channel_id)
        return {member.id: member.display_name for member in _humans(channel)}

    def roster_voice(self, link: Link) -> dict[int, str]:
        """
        Everyone actually in the link's voice channel -- tracked completely
        separately from roster_text(): who's in one is not reliably who's
        in the other, and participation_equality_voice needs this roster on
        its own, not a text+voice union (that used to make a voice
        intervention look at everyone in the text channel too, as though
        they were all also on the call).
        """

        channel = (
            self.client.get_channel(link.voice_channel_id)
            if link.voice_channel_id
            else None
        )
        return {member.id: member.display_name for member in _humans(channel)}

    def _can_see(self, user_id: int, channel_id: int) -> bool:
        channel = self.client.get_channel(channel_id)
        guild = getattr(channel, "guild", None)
        member = guild.get_member(user_id) if guild is not None else None
        return member is not None and channel.permissions_for(member).view_channel

    def dm_links(self, user_id: int) -> list[Link]:
        """
        The links that let this user DM the bot: those with DMs turned on
        (/mulca dms) whose text channel the user can see. None means the bot
        doesn't take their DMs -- the default, since DMs start off.
        """

        return [
            link
            for link in self.links()
            if link.allow_dms and self._can_see(user_id, link.text_channel_id)
        ]

    def dm_link(self, user_id: int) -> Link | None:
        """
        The group memory a DM from this user may read, if the bot takes
        their DMs at all: the DM-enabled channel they last spoke in, else
        the first DM-enabled channel they can see.
        """

        allowed = self.dm_links(user_id)
        if not allowed:
            return None

        last = self.store.last_link_for(user_id)
        return last if last in allowed else allowed[0]

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

        text_channel = self.client.get_channel(link.text_channel_id)
        me = getattr(getattr(channel, "guild", None), "me", None)
        missing = missing_permissions(channel, me, voice=True) if me is not None else []
        if missing:
            await self.notices.raise_(
                f"voice:{link.name}",
                text_channel,
                messages.voice_join_failed(link.voice_channel_id, missing),
            )
            return
        self.notices.forget(f"voice:{link.name}")

        logger.info("Joining voice channel %s for %s", channel, link.name)
        voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)

        bridge = VoiceBridge(
            scope=Scope(
                conversation_id=link.conversation_id,
                bot_name=self.name,
                listening_mode=link.listening_mode,
            ),
            registry=self.registry,
            voice_client=voice_client,
            reply_channel=self.client.get_channel(link.text_channel_id),
            post_voice_transcripts=link.post_voice_transcripts,
            roster=lambda: self.roster_voice(link),
            on_unhealthy=lambda: self._rejoin_voice(link),
            on_active=lambda: self.voice_active(link),
            on_reachable=lambda reachable: self.server_reachable(text_channel, reachable),
        )
        self.voice[link.name] = bridge
        await bridge.start()

    async def leave_voice(self, link: Link) -> None:
        bridge = self.voice.pop(link.name, None)
        if bridge is None:
            return

        logger.info("Leaving the voice channel of %s", link.name)
        await bridge.disconnect()

    async def _rejoin_voice(self, link: Link) -> None:
        """
        Watchdog tier 2 -- a full reset, given whenever the bridge decides
        a lighter fix (reopening the MUCA-Server session) didn't
        verifiably work, or its own tick loop died outright. Server-side
        logs only (see bridge.py); never announced to the group.
        """

        await self.leave_voice(link)
        await self.join_voice(link)

    async def sync_voice(self, link: Link) -> None:
        channel = (
            self.client.get_channel(link.voice_channel_id)
            if link.voice_channel_id is not None
            else None
        )
        if _humans(channel) and not self.paused and not self.notices.is_active(LIMIT):
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
        await self.close_dms_of(link)

    async def close_dms_of(self, link: Link) -> None:
        """Close the DM sessions reading this link's memory (DMs turned off)."""

        for conversation_id, session in list(self.registry.sessions.items()):
            if session.scope.linked_conversation_id == link.conversation_id:
                await self.registry.close(conversation_id, wait=RESTART_WAIT_SECONDS)

    # ------------------------------------------------------------------
    # Control: /restart, /mulca stop|start|restart
    # ------------------------------------------------------------------

    async def arm_listening(self, link: Link, *, reply_channel) -> None:
        """
        push_to_talk mode only: a participant pressed /listen or the
        button -- a toggle, the server decides whether this starts or
        stops a window. A no-op server-side in ambient mode
        (Conversation.arm_listening), so this is safe to call regardless
        of which mode MUCA-Server is running.
        """

        await self.registry.run(
            Scope(
                conversation_id=link.conversation_id,
                bot_name=self.name,
                listening_mode=link.listening_mode,
            ),
            lambda client: client.arm_listening(),
            reply_channel=reply_channel,
        )

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
        self.notices.forget(PAUSED)
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
                    allow_dms=link.allow_dms,
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

        # A bot's own model outranks the one set for every bot, which
        # outranks MUCA-Server's own default (unknown here).
        models = tuple(
            f"{own} (this bot)" if own else f"{everyone} (all bots)" if everyone else "server default"
            for own, everyone in zip(
                self.store.models_for(self.user_id),
                self.store.server_models(),
            )
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
            models=models,
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
        # on_ready comes again after every reconnect to Discord: one watch.
        if self._watch is None or self._watch.done():
            self._watch = asyncio.create_task(self._watch_limits())

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

        if message.author.bot or not message.content:
            return

        channel = message.channel
        tagged = self.client.user is not None and self.client.user in getattr(
            message, "mentions", []
        )
        is_dm = isinstance(channel, discord.DMChannel)
        link: Link | None = None

        if is_dm:
            # DMs are off unless an admin turned them on for a linked channel
            # (/mulca dms), and then only for people who can see that
            # channel. Such a DM may also read that channel's group memory.
            linked = self.dm_link(message.author.id)
            if linked is None:
                if not self.paused:
                    await messages.post(channel, DMS_OFF_REPLY)
                return

            scope = Scope(
                conversation_id=f"dm:{message.author.id}",
                is_dm=True,
                linked_conversation_id=linked.conversation_id,
                bot_name=self.name,
            )
        else:
            link = self.link_for_channel(message.channel.id)
            if link is None:
                # Not a channel linked to this bot.
                return
            scope = Scope(
                conversation_id=link.conversation_id,
                bot_name=self.name,
                listening_mode=link.listening_mode,
            )

        if self.paused:
            await self._announce(PAUSED, channel, messages.PAUSED, tagged=tagged)
            return

        if link is not None:
            self.store.remember_speaker(message.author.id, link.text_channel_id)

        if await self.over_limit(channel, tagged=tagged):
            return

        warned = False
        if self.usage.mark_active(self.user_id, scope.conversation_id):
            warned = await self._warn_if_low(channel)

        roster = self.roster_text(link) if link is not None else {}
        if link is not None and not roster:
            roster = await _roster(message.channel)

        async def send(muca_client) -> None:
            if link is not None:
                await muca_client.send_participants(roster, modality="text")

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
            await self._announce(OFFLINE, channel, messages.OFFLINE, tagged=tagged)
            return

        await self.notices.resolve(OFFLINE, messages.BACK_ONLINE)

        if tagged:
            if getattr(message, "attachments", None) or getattr(message, "stickers", None):
                await messages.post(channel, messages.ATTACHMENTS)
            await self.notices.remind(channel, skip=(WARNING,) if warned else ())

    # ------------------------------------------------------------------
    # Usage limits, and telling users what's wrong (messages.py)
    # ------------------------------------------------------------------

    async def _announce(self, problem: str, channel, text: str, *, tagged: bool) -> None:
        """Once when the problem is raised; again only for an @mention."""

        if not await self.notices.raise_(problem, channel, text) and tagged:
            await messages.post(channel, self.notices.text(problem) or text)

    async def over_limit(self, channel, *, tagged: bool = False) -> bool:
        """
        Whether this bot is over a usage limit. The first time, it says so
        and stops: out of voice, its sessions closed (memory saved).
        """

        budget = self.usage.check(self.user_id)
        if budget is None:
            return False

        if await self.notices.raise_(LIMIT, channel, messages.limit_reached(budget)):
            logger.info(
                "%s is over its %s %s limit (%d/%d min)",
                self.name,
                budget.scope,
                budget.kind,
                budget.used,
                budget.limit,
            )
            # Not awaited: this may run inside a voice bridge's own tick,
            # which leaving voice cancels.
            self._spawn(self._stop_for_limit())
        elif tagged:
            await messages.post(channel, self.notices.text(LIMIT))

        return True

    async def _stop_for_limit(self) -> None:
        for link in self.links():
            await self.leave_voice(link)
        for conversation_id in list(self.registry.sessions):
            await self.registry.close(conversation_id, wait=RESTART_WAIT_SECONDS)

    async def _warn_if_low(self, channel) -> bool:
        """The heads-up before a limit, once; True if it was just posted."""

        budget = self.usage.tightest(self.user_id)
        if budget is None or budget.left > WARNING_MINUTES:
            return False

        return await self.notices.raise_(WARNING, channel, messages.limit_warning(budget))

    async def voice_active(self, link: Link) -> bool:
        """
        Someone holds the floor in voice, or MULCA is heard: counts this
        minute. False when over a limit, so the bridge sends nothing.
        """

        if not self.usage.is_new_minute(link.conversation_id):
            return True

        channel = self.client.get_channel(link.text_channel_id)
        if await self.over_limit(channel):
            return False

        self.usage.mark_active(self.user_id, link.conversation_id)
        await self._warn_if_low(channel)
        return True

    async def server_reachable(self, channel, reachable: bool) -> None:
        if reachable:
            await self.notices.resolve(OFFLINE, messages.BACK_ONLINE)
        else:
            await self.notices.raise_(OFFLINE, channel, messages.OFFLINE)

    def _on_reply(self, session: ScopeSession, is_final: bool) -> None:
        self.usage.mark_active(self.user_id, session.scope.conversation_id)
        if is_final:
            self.notices.forget(TURN_FAILED)

    async def _on_server_error(self, session: ScopeSession, message: str) -> None:
        await self.notices.raise_(TURN_FAILED, session.replies.channel, messages.TURN_FAILED)

    async def recheck_limits(self) -> None:
        """After a new day or week, or a changed limit: lift what's over."""

        if self.notices.is_active(LIMIT) and self.usage.check(self.user_id) is None:
            logger.info("%s is back under its usage limits", self.name)
            await self.notices.resolve(LIMIT, messages.AVAILABLE_AGAIN)
            await self._sync_all_voice()

        budget = self.usage.tightest(self.user_id)
        if budget is None or budget.left > WARNING_MINUTES:
            self.notices.forget(WARNING)

    async def _watch_limits(self) -> None:
        while True:
            await asyncio.sleep(LIMIT_CHECK_SECONDS)
            try:
                await self.recheck_limits()
            except Exception:
                logger.exception("Checking %s's usage limits failed", self.name)

    def _spawn(self, coroutine) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close(self) -> None:
        for task in [*self._tasks, self._watch]:
            if task is not None:
                task.cancel()

        for bridge in list(self.voice.values()):
            await bridge.disconnect()
        self.voice.clear()

        await self.registry.close_all()


# ----------------------------------------------------------------------
# The bots of this process
# ----------------------------------------------------------------------


ClientFactory = Callable[[], discord.Client]

# How long /mulca bot add waits for a new bot to come online.
BOT_READY_TIMEOUT_SECONDS = 30.0

# Waits before restarting an added bot that crashed, doubling up to the last.
BOT_RETRY_DELAYS_SECONDS = (5.0, 300.0)


class BotManager:
    """
    The bots this process runs: the primary one (its token is a Swarm
    secret; it carries the slash commands) and those added with /mulca bot
    add, each in its own supervised task -- one bot that fails never stops
    the others.
    """

    def __init__(
        self,
        bots: list[BotRuntime],
        *,
        store: LinkStore | None = None,
        client_factory: ClientFactory | None = None,
        primary_token: str | None = None,
    ) -> None:
        if not bots:
            raise ValueError("a BotManager needs at least one bot")
        self.bots = bots
        self.store = store
        self.primary_token = primary_token
        self._client_factory = client_factory

        # Added bots: what each is doing ("online", "failed: ...", ...).
        self.states: dict[int, str] = {}
        self._tasks: dict[int, asyncio.Task[None]] = {}
        self._ready: dict[int, asyncio.Event] = {}

    # -- added bots --------------------------------------------------------

    async def start_added_bots(self) -> None:
        """At startup: every bot added with /mulca bot add."""

        if self.store is None:
            return

        for record in self.store.added_bots():
            await self.start_bot(record, wait=False)

    async def start_bot(self, record: BotRecord, *, wait: bool = True) -> str:
        """Start an added bot; with `wait`, until it's online or has failed."""

        if record.bot_id in self._tasks:
            return self.states.get(record.bot_id, "starting")

        self.states[record.bot_id] = "starting"
        self._ready[record.bot_id] = asyncio.Event()
        task = asyncio.create_task(
            self._supervise(record),
            name=f"bot-{record.bot_id}",
        )
        self._tasks[record.bot_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(record.bot_id, None))

        if wait:
            ready = asyncio.create_task(self._ready[record.bot_id].wait())
            await asyncio.wait(
                {ready, task},
                timeout=BOT_READY_TIMEOUT_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            ready.cancel()

        return self.states[record.bot_id]

    async def stop_bot(self, bot_id: int) -> None:
        task = self._tasks.get(bot_id)
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self.states.pop(bot_id, None)

    async def stop_added_bots(self) -> None:
        for bot_id in list(self._tasks):
            await self.stop_bot(bot_id)

    async def _supervise(self, record: BotRecord) -> None:
        delay, maximum = BOT_RETRY_DELAYS_SECONDS

        while True:
            client = self._client_factory()
            runtime: BotRuntime = client.mulca_runtime

            async def online(_runtime: BotRuntime) -> None:
                self.states[record.bot_id] = "online"
                self._ready[record.bot_id].set()

            runtime.after_ready.append(online)
            self.bots.append(runtime)
            try:
                async with client:
                    await client.start(record.token)
                return
            except discord.LoginFailure:
                self.states[record.bot_id] = (
                    "failed: Discord rejected its token (reset it in the "
                    "Developer Portal, then /mulca bot add the new one)"
                )
                logger.error("Bot %s: its token was rejected", record.name)
                return
            except discord.PrivilegedIntentsRequired:
                self.states[record.bot_id] = (
                    "failed: turn on the Message Content and Server Members "
                    "intents (Developer Portal, Bot page), then /mulca bot add it again"
                )
                logger.error("Bot %s: privileged intents are off", record.name)
                return
            except Exception:
                logger.exception("Bot %s crashed; restarting in %.0f s", record.name, delay)
                self.states[record.bot_id] = f"restarting in {delay:.0f} s after an error"
            finally:
                with suppress(Exception):
                    await runtime.close()
                if runtime in self.bots:
                    self.bots.remove(runtime)

            await asyncio.sleep(delay)
            delay = min(delay * 2, maximum)

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

        Matching by id is always exact -- ids are unique by construction, so
        that branch can never be ambiguous. Matching by name can be: two
        bots running from the same code default to the same Discord
        username until someone renames one, and a command that named one
        specific bot (unlike "all") picking a silently arbitrary one of
        several matches would be a real foot-gun -- e.g. /mulca link
        linking whichever bot happened to be resolved first, not the one
        actually chosen. Raises AmbiguousBotName instead.
        """

        bots = self.in_guild(guild_id)
        if target is None or target.strip().lower() in ("", "all"):
            return bots

        wanted = target.strip().lower()

        by_id = [bot for bot in bots if str(bot.user_id) == wanted]
        if by_id:
            return by_id

        by_name = [bot for bot in bots if bot.name.lower() == wanted]
        if len(by_name) > 1:
            raise AmbiguousBotName(target, by_name)

        return by_name
