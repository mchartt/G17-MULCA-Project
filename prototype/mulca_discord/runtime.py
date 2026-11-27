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
import re
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field

import discord

from . import courses, messages
from .names import unique_in_channel
from .attachments import read_attachments
from .links import BotRecord, Link, LinkStore, link_for_channel
from .messages import Notices
from .muca_client import MucaWsClient
from .permissions import missing_permissions
from .sessions import RESTART_WAIT_SECONDS, Scope, ScopeSession, SessionRegistry
from .usage import LISTEN, STOP, TEXT, UsageMeter

logger = logging.getLogger(__name__)

ReadyHook = Callable[["BotRuntime"], Awaitable[None]]


def readable_mentions(text: str, me, roles=()) -> str:
    """
    The bot's own @mention as "@MULCA" -- MUCA-Server only sees the raw
    "<@1557...>" otherwise. Found live (15 Oct): "could you look up whether
    smoking is healthy @MULCA" went unanswered, judged an unknown role tag.
    roles: the bot's own role(s) -- found live (16 Oct), students mention
    the role "@MULCA" as often as the bot itself.
    """

    if me is not None:
        text = text.replace(f"<@{me.id}>", "@MULCA").replace(f"<@!{me.id}>", "@MULCA")
    for role in roles:
        text = text.replace(f"<@&{role.id}>", "@MULCA")
    return text


def message_parts(message) -> tuple[str, list]:
    """
    A message's text and files, a forwarded message's included -- Discord
    puts those in a snapshot, not in the message itself. Found live (21-24
    Oct): students shared files, then asked "can you read the file I
    shared?", and MULCA had nothing. Blank text counts as none.
    """

    parts = [message.content] if (message.content or "").strip() else []
    files = list(getattr(message, "attachments", None) or [])
    for snapshot in getattr(message, "message_snapshots", None) or []:
        if (snapshot.content or "").strip():
            parts.append(f"[Forwarded message:]\n{snapshot.content}")
        files.extend(getattr(snapshot, "attachments", None) or [])
    return "\n\n".join(parts), files


def own_roles(message, me) -> list:
    """The roles mentioned in the message that are this bot's own."""

    if me is None:
        return []
    return [
        role
        for role in getattr(message, "role_mentions", None) or []
        if getattr(getattr(role, "tags", None), "bot_id", None) == me.id
    ]


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
LISTEN_ONLY = "listen_only"
TEXT_ONLY = "text_only"
OFFLINE = "offline"
PAUSED = "paused"
TURN_FAILED = "turn_failed"

# The stages a bot goes through as it spends its budget (usage.STAGES), in
# order, each announced once: a heads-up, replies in text while it still
# listens in voice, text only (out of voice), a full stop.
STAGE_NOTICES = (WARNING, LISTEN_ONLY, TEXT_ONLY, LIMIT)
STAGE_TEXTS = (
    messages.limit_warning,
    messages.listening_only,
    messages.text_only,
    messages.limit_reached,
)

# How often a bot checks whether a limit reset (a new day, week or month).
LIMIT_CHECK_SECONDS = 60.0

# A safety net for the "MULCA is typing..." indicator below -- Discord
# clears it the moment any message actually arrives, so this only matters
# if a reply never comes at all (e.g. the session died silently); without
# a cap, the indicator would otherwise re-trigger forever.
TYPING_INDICATOR_MAX_SECONDS = 30.0

# How often the session reminder (daily greeting/first-session message) is
# allowed to repeat on its own, in a given conversation -- a rolling
# cooldown since the last time it actually showed, not a calendar-day
# reset. See BotRuntime._greet_if_due.
GREETING_COOLDOWN_SECONDS = 2 * 24 * 3600

# A call shorter than this (someone popping in and out) gets no diary
# reminder when it ends: it wasn't a work session.
CALL_REMINDER_MIN_SECONDS = 120

# Display names that don't count as a conversation's "first real message"
# for the reminder's own cooldown clock -- test/admin accounts used while
# setting a channel up, not actual participants. Matched case-insensitively
# against the author's display name. Bot messages (MULCA's own) are
# already excluded earlier in on_message, before this is ever checked.
GREETING_EXCLUDED_AUTHOR_NAMES = {"mats", "admin"}


async def _roster(channel: discord.abc.Messageable) -> dict[int, str]:
    members = getattr(channel, "members", [])
    return {member.id: member.display_name for member in members if not member.bot}


_NAME_PARTS = re.compile(r"[._\-\s]+")
_NOT_A_NAME = re.compile(r"^((group|gruppo)\d*|\d+)$", re.IGNORECASE)


def spoken_names(names: dict[int, str]) -> dict[int, str]:
    """
    "wake" and "wake_v2": the names MULCA calls people by -- the first name
    from a display name ("name_surname_group11" is Name), with the surname
    too when two people here share it. Found in the 15-28 Oct exports: MULCA
    read whole display names aloud.
    """

    parts = {
        user_id: [
            part.capitalize()
            for part in _NAME_PARTS.split(name)
            if part and not _NOT_A_NAME.match(part)
        ]
        or [name]
        for user_id, name in names.items()
    }
    firsts = [words[0].lower() for words in parts.values()]
    return {
        user_id: " ".join(words[:2] if firsts.count(words[0].lower()) > 1 else words[:1])
        for user_id, words in parts.items()
    }


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
    # The Group Coordinator's bridge, set by install_coordinator when it is on
    # (a class attribute, not a field: None means MULCA exactly as before).
    coordinator_chat = None

    voice: dict[str, object] = field(default_factory=dict)
    paused: bool = False
    ready_at: float | None = None

    # Called after each on_ready, e.g. to sync slash commands.
    after_ready: list[ReadyHook] = field(default_factory=list)

    usage: UsageMeter | None = None
    notices: Notices = field(default_factory=Notices)
    _tasks: set[asyncio.Task[None]] = field(default_factory=set, repr=False)
    _watch: asyncio.Task[None] | None = field(default=None, repr=False)
    # The last greeting message (FIRST_SESSION_MESSAGE or DAILY_GREETING)
    # actually posted per conversation -- _replace_greeting deletes this
    # before posting the next one, found live: otherwise every day's own
    # copy just piles up as channel noise. In-memory only: losing track of
    # it across a restart just means one old copy is left behind once, not
    # a correctness issue -- unlike the greeted-date/had-a-session state
    # itself (self.store.greeting_state), which is persisted. Found live:
    # that state used to be in-memory too, and a restart between /mulca
    # greet and a conversation's real first message reset it, letting the
    # reminder post a second time the same day.
    _last_greeting_message: dict[str, object] = field(default_factory=dict, repr=False)
    # Same, for CALL_ENDED_REMINDER, keyed on link name.
    _last_call_reminder: dict[str, object] = field(default_factory=dict, repr=False)
    # When MULCA joined each link's current call; kept across a watchdog
    # rejoin, which is the same call.
    _call_started_at: dict[str, float] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.usage is None:
            self.usage = UsageMeter(self.store)
        self.registry.on_reply = self._on_reply
        self.registry.on_server_error = self._on_server_error
        self.registry.on_usage = self._on_usage

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

    def _channel_name_for(self, link: Link) -> str:
        """The linked text channel's own Discord name, or "" if unresolvable."""

        channel = self.client.get_channel(link.text_channel_id)
        return getattr(channel, "name", "") or ""

    def course_choice(self, guild_id: int) -> tuple[str, str]:
        """
        (course, where that comes from) for this bot's sessions in a
        Discord server: its own /mulca course setting there, else the
        server's, else the one course the server's name names (courses.
        detect, read live so a rename needs no restart), else the default.
        """

        for setting, source in (
            (self.store.course_setting(guild_id, self.user_id), "bot setting"),
            (self.store.course_setting(guild_id), "server setting"),
        ):
            if setting in courses.COURSES:
                return setting, source

        guild = self.client.get_guild(guild_id)
        detected = courses.detect(getattr(guild, "name", "") or "")
        if detected is not None:
            return detected, "server name"
        return courses.DEFAULT_COURSE, "default"

    def course_for(self, guild_id: int) -> str:
        return self.course_choice(guild_id)[0]

    def roster_text(self, link: Link) -> dict[int, str]:
        """Everyone in the link's text channel."""

        channel = self.client.get_channel(link.text_channel_id)
        names = {member.id: member.display_name for member in _humans(channel)}
        # Two people with the same name are two names for the model (names.py).
        return unique_in_channel(spoken_names(names) if link.listening_mode in courses.WAKE_MODES else names)

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
        names = {member.id: member.display_name for member in _humans(channel)}
        # Two people with the same name are two names for the model (names.py).
        return unique_in_channel(spoken_names(names) if link.listening_mode in courses.WAKE_MODES else names)

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

    def _greet_if_due(self, conversation_id: str) -> bool:
        """
        True (and marks it) only when the reminder is actually due for
        this conversation: a rolling GREETING_COOLDOWN_SECONDS since the
        last time it showed, not a calendar-day reset -- so it can't
        repeat more than once every two days no matter how many messages
        arrive in between.

        last_greeted_at == 0 means the cooldown clock hasn't started at
        all yet (a conversation's first-ever qualifying message, or a
        freshly migrated row) -- starts it here, without firing, rather
        than greeting the very first message anyone sends. Two full days
        then have to pass before the first real reminder shows.

        Persisted (self.store), not in-memory: found live, a bot restart
        between /mulca greet and a conversation's real first message
        reset an in-memory version of this, letting the reminder post
        again right away. No await in here on purpose: discord.py
        dispatches on_message concurrently, and this check-then-mark has
        to be atomic against two messages arriving at once (sqlite3's own
        calls are synchronous, so nothing yields control in between).
        """

        now = time.time()
        last_greeted_at, had_a_session = self.store.greeting_state(conversation_id)
        if last_greeted_at != 0 and now - last_greeted_at < GREETING_COOLDOWN_SECONDS:
            return False

        due = last_greeted_at != 0
        self.store.set_greeting_state(
            conversation_id, last_greeted_at=now, had_a_session=had_a_session
        )
        return due

    def _had_a_session(self, conversation_id: str) -> bool:
        return self.store.greeting_state(conversation_id)[1]

    def _mark_had_a_session(self, conversation_id: str) -> None:
        last_greeted_at, _ = self.store.greeting_state(conversation_id)
        self.store.set_greeting_state(
            conversation_id, last_greeted_at=last_greeted_at, had_a_session=True
        )

    async def _replace_greeting(
        self, channel, conversation_id: str, text: str
    ) -> str | None:
        """
        Deletes whichever greeting (FIRST_SESSION_MESSAGE or DAILY_GREETING)
        was last posted in this conversation, then posts a new one --
        found live, otherwise every day's own copy just piles up as
        channel noise. A failed delete (already removed, permissions
        changed) is not worth failing the new post over. Returns None on
        success, or a short description of why the new post itself failed
        -- found live, a command reporting "Posted" regardless of whether
        it actually was is worse than useless, it actively hides a real
        problem with that specific channel/link.
        """

        previous = self._last_greeting_message.pop(conversation_id, None)
        if previous is not None:
            with suppress(Exception):
                await previous.delete()

        try:
            self._last_greeting_message[conversation_id] = await channel.send(text)
            return None
        except Exception as exc:
            logger.warning("Could not post a greeting in %s", channel, exc_info=True)
            return str(exc) or type(exc).__name__

    async def post_first_session_greeting(
        self, channel, conversation_id: str
    ) -> str | None:
        """
        /mulca greet: a channel's first-ever session, right after it's
        linked and announced, has no earlier visit to welcome them back
        from -- posts messages.FIRST_SESSION_MESSAGE instead of the usual
        DAILY_GREETING, and resets the cooldown clock (GREETING_COOLDOWN_
        SECONDS) so on_message's automatic reminder doesn't also fire
        again right away. Deliberately does not mark had_a_session: this
        is an admin pre-announcing the channel, not a real session -- if
        the group's actual first message doesn't arrive until days later,
        it should still get FIRST_SESSION_MESSAGE too, not "Welcome back!".

        Only resets the cooldown if the post actually succeeded -- a
        failed attempt shouldn't also suppress on_message's own, later
        retry via the automatic reminder.

        Returns None on success, or a short description of the failure.
        """

        error = await self._replace_greeting(
            channel, conversation_id, messages.FIRST_SESSION_MESSAGE
        )
        if error is None:
            _, had_a_session = self.store.greeting_state(conversation_id)
            self.store.set_greeting_state(
                conversation_id,
                last_greeted_at=time.time(),
                had_a_session=had_a_session,
            )
        return error

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
                channel_name=self._channel_name_for(link),
                course=self.course_for(link.guild_id),
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
        self._call_started_at.setdefault(link.name, time.time())
        await bridge.start()

    async def leave_voice(self, link: Link, *, rejoining: bool = False) -> None:
        if not rejoining:
            self._call_started_at.pop(link.name, None)
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

        await self.leave_voice(link, rejoining=True)
        await self.join_voice(link)

    async def sync_voice(self, link: Link) -> None:
        channel = (
            self.client.get_channel(link.voice_channel_id)
            if link.voice_channel_id is not None
            else None
        )
        if (
            _humans(channel)
            and not self.paused
            and not self.notices.is_active(TEXT_ONLY)
            and not self.notices.is_active(LIMIT)
        ):
            await self.join_voice(link)
        else:
            started = self._call_started_at.get(link.name)
            was_in_voice = link.name in self.voice
            await self.leave_voice(link)
            if (
                was_in_voice
                and not _humans(channel)
                and started is not None
                and time.time() - started >= CALL_REMINDER_MIN_SECONDS
            ):
                await self._post_call_ended_reminder(link)

    async def _post_call_ended_reminder(self, link: Link) -> None:
        """
        Everyone left the call: the diary/thumbs reminder in the text
        channel, replacing the previous one (found live: copies pile up).
        """

        channel = self.client.get_channel(link.text_channel_id)
        if channel is None:
            return

        previous = self._last_call_reminder.pop(link.name, None)
        if previous is not None:
            with suppress(Exception):
                await previous.delete()

        try:
            self._last_call_reminder[link.name] = await channel.send(
                messages.CALL_ENDED_REMINDER
            )
        except Exception:
            logger.warning("Could not post the call-ended reminder in %s", channel, exc_info=True)

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
        transcript setting starts a new voice bridge; a changed listening
        mode also restarts the session, so it reopens in that mode.
        """

        if previous is not None and previous != link:
            await self.leave_voice(previous)
        if previous is not None and previous.listening_mode != link.listening_mode:
            await self.registry.restart(link.conversation_id)

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

    async def arm_listening(self, link: Link, *, reply_channel) -> bool | None:
        """
        "toggle" mode only: a participant pressed /listen or the button --
        a toggle, the server decides whether this starts or stops a
        window. A no-op server-side in ambient or "transcribe" mode
        (Conversation.arm_listening), so this is safe to call regardless
        of which mode MUCA-Server is running.

        Returns the resulting state MUCA-Server reports back (True: now
        listening, False: now not), or None if nothing came back (e.g.
        ambient/"transcribe" mode, where the server never replies to this
        at all).
        """

        result: list[bool | None] = [None]

        async def action(client: MucaWsClient) -> None:
            result[0] = await client.arm_listening()

        await self.registry.run(
            Scope(
                conversation_id=link.conversation_id,
                bot_name=self.name,
                listening_mode=link.listening_mode,
                channel_name=self._channel_name_for(link),
                course=self.course_for(link.guild_id),
            ),
            action,
            reply_channel=reply_channel,
        )
        return result[0]

    async def restart_link(self, link: Link) -> RestartOutcome:
        """
        Restart one link's MUCA-Server session: the server reconnects its
        provider (OpenAI) from scratch and reloads the saved memory. In
        voice: a genuine fresh connection too, not just a roster refresh --
        found live, running /restart while in voice left the existing
        voice connection untouched, only silently refreshing its roster
        (update_participants() alone), not actually reconnecting anything.
        Already in voice: a full leave-and-rejoin (_rejoin_voice, the same
        full reset the watchdog uses). Not currently in voice at all (it
        had left because it was empty, or never joined): joins now if
        someone's actually there (sync_voice), rather than staying out
        just because restarting doesn't on its own imply anyone's present.
        """

        confirmed = await self.registry.restart(link.conversation_id)

        if link.voice_channel_id is not None:
            if link.name in self.voice:
                await self._rejoin_voice(link)
            else:
                await self.sync_voice(link)

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

        for guild_id in sorted({link.guild_id for link in links}):
            course, source = self.course_choice(guild_id)
            guild = self.client.get_guild(guild_id)
            logger.info(
                "%s in server %r: course %s (%s)",
                self.name,
                getattr(guild, "name", guild_id),
                course,
                source,
            )

        await self.recheck_limits()
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

        content, attachments = message_parts(message)
        if message.author.bot or not (content or attachments):
            return

        channel = message.channel
        my_roles = own_roles(message, self.client.user)
        tagged = bool(my_roles) or (
            self.client.user is not None
            and self.client.user in getattr(message, "mentions", [])
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
                course=self.course_for(linked.guild_id),
            )
        else:
            # A web space's invite link pasted in any channel links it (one
            # step, coordinator/bridge.py invite). The main bot only, once.
            coordinator = self.coordinator_chat
            if self.is_primary and coordinator is not None and hasattr(coordinator, "invite"):
                if await coordinator.invite(message):
                    return
            link = self.link_for_channel(message.channel.id)
            if link is None:
                # Not a channel linked to this bot.
                return
            scope = Scope(
                conversation_id=link.conversation_id,
                bot_name=self.name,
                listening_mode=link.listening_mode,
                channel_name=getattr(message.channel, "name", "") or "",
                course=self.course_for(link.guild_id),
            )

        if self.paused:
            await self._announce(PAUSED, channel, messages.PAUSED, tagged=tagged)
            return

        # Group channels only -- a DM is a private, individual conversation,
        # not the kind of per-session group work the diary/usefulness-signal
        # reminders are about. Test/admin accounts (GREETING_EXCLUDED_AUTHOR_
        # NAMES) don't count as the conversation's own activity for this at
        # all -- their messages neither start the cooldown clock nor get a
        # reminder of their own.
        is_real_participant = (
            message.author.display_name.strip().lower()
            not in GREETING_EXCLUDED_AUTHOR_NAMES
        )
        due_for_greeting = (
            link is not None
            and is_real_participant
            and self._greet_if_due(scope.conversation_id)
        )
        if due_for_greeting:
            # Still no real session yet (e.g. /mulca greet ran days ago,
            # but this is genuinely the group's first message) -- this one
            # gets FIRST_SESSION_MESSAGE too, not a "Welcome back!" that
            # wouldn't be true yet.
            had_session = self._had_a_session(scope.conversation_id)
            if not had_session:
                self._mark_had_a_session(scope.conversation_id)
            await self._replace_greeting(
                channel,
                scope.conversation_id,
                messages.DAILY_GREETING if had_session else messages.FIRST_SESSION_MESSAGE,
            )

        if link is not None:
            self.store.remember_speaker(message.author.id, link.text_channel_id)

        if await self.over_limit(channel, tagged=tagged):
            return

        # Group Coordinator on: a message for Cadence (named, @mentioned, or a
        # follow-up) is answered by the coordinator from the project, like on
        # the web app; everything else goes on as before.
        coordinator = self.coordinator_chat
        offered_to_ask = False  # a follow-up the coordinator also asked Cadence about
        if link is not None and coordinator is not None and not attachments:
            if await coordinator.chat(channel, message.author.id, content, tagged=tagged):
                return
            offered_to_ask = coordinator.offered(content)

        roster = self.roster_text(link) if link is not None else {}
        if link is not None and not roster:
            roster = await _roster(message.channel)
        # "wake" and "wake_v2": the author by the same name as in the roster.
        first_names = link is not None and link.listening_mode in courses.WAKE_MODES
        if first_names:
            roster = spoken_names(
                {message.author.id: message.author.display_name, **roster}
            )

        # Read once, not again on a reconnect's resend.
        attached = await read_attachments(attachments)

        async def send(muca_client) -> None:
            if link is not None:
                await muca_client.send_participants(roster, modality="text")

            # Shows "MULCA is typing..." for as long as this reply takes to
            # start arriving -- found live, a web-search-backed reply can
            # take several seconds with nothing else visible meanwhile.
            # Temporarily wraps the client's own handler rather than
            # touching ReplyDispatcher: restores it the moment the first
            # piece of a reply actually arrives (for either modality, same
            # as the real handler already tees them apart), so every later
            # delta goes through the real handler completely unaffected.
            original_handler = muca_client.on_assistant_text
            original_no_reply = muca_client.on_no_reply
            typing_done = asyncio.Event()

            def _restore_handlers() -> None:
                muca_client.on_assistant_text = original_handler
                muca_client.on_no_reply = original_no_reply

            async def on_first_text(text, is_final, modality) -> None:
                if not typing_done.is_set():
                    typing_done.set()
                    _restore_handlers()
                if original_handler is not None:
                    await original_handler(text, is_final, modality)

            async def on_no_reply() -> None:
                # The server's judgment fired nothing for this turn -- no
                # reply is coming, so there's nothing to keep "typing" for.
                if not typing_done.is_set():
                    typing_done.set()
                    _restore_handlers()
                if original_no_reply is not None:
                    await original_no_reply()

            muca_client.on_assistant_text = on_first_text
            muca_client.on_no_reply = on_no_reply

            async def show_typing() -> None:
                async with channel.typing():
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(
                            typing_done.wait(),
                            timeout=TYPING_INDICATOR_MAX_SECONDS,
                        )
                if not typing_done.is_set():
                    # Neither a reply nor a no_reply signal arrived in time
                    # -- restore the real handlers anyway, so a late reply
                    # isn't silently eaten.
                    _restore_handlers()

            asyncio.create_task(show_typing())

            await muca_client.send_user_text(
                speaker=message.author.id,
                speaker_name=(
                    roster[message.author.id]
                    if first_names
                    # The roster's name: "Luca 2" when two Lucas are here (names.py).
                    else roster.get(message.author.id, message.author.display_name)
                ),
                text=readable_mentions(content, self.client.user, my_roles),
                mentions_assistant=tagged,
                attachments=attached,
                # Only when set: the lab's call stays as it was otherwise.
                **({"offered_to_ask": True} if offered_to_ask else {}),
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
            unreadable = any(not attachment.readable for attachment in attached)
            if unreadable or getattr(message, "stickers", None):
                await messages.post(channel, messages.ATTACHMENTS)
            await self.notices.remind(channel)

    # ------------------------------------------------------------------
    # Usage limits, and telling users what's wrong (messages.py)
    # ------------------------------------------------------------------

    async def _announce(self, problem: str, channel, text: str, *, tagged: bool) -> None:
        """Once when the problem is raised; again only for an @mention."""

        if not await self.notices.raise_(problem, channel, text) and tagged:
            await messages.post(channel, self.notices.text(problem) or text)

    async def over_limit(self, channel, *, tagged: bool = False) -> bool:
        """Whether this bot is stopped by a usage limit (apply_stage)."""

        if not self.notices.is_active(LIMIT):
            return False

        if tagged:
            await messages.post(channel, self.notices.text(LIMIT))
        return True

    async def apply_stage(self, channel=None) -> None:
        """
        Bring the bot to the stage its spending puts it at (usage.stage):
        announced once going up, in `channel` (else its first linked one);
        lifted with one message going down, after a reset or a raised limit.
        """

        level, budget = self.usage.stage(self.user_id)
        above = [p for p in STAGE_NOTICES[level:] if self.notices.is_active(p)]

        if above:
            logger.info("%s is back to usage stage %d", self.name, level)
            for problem in above[:-1]:
                self.notices.forget(problem)
            await self.notices.resolve(above[-1], messages.stage_lifted(level))
        elif level and not self.notices.is_active(STAGE_NOTICES[level - 1]):
            logger.info(
                "%s reached usage stage %d: %s %s limit at %.0f%% ($%.2f of $%.2f)",
                self.name,
                level,
                budget.scope,
                budget.kind,
                budget.share * 100,
                budget.used,
                budget.limit,
            )
            channel = channel or self._first_text_channel()
            for problem in STAGE_NOTICES[: level - 1]:
                self.notices.hold(problem, channel)
            await self.notices.raise_(
                STAGE_NOTICES[level - 1], channel, STAGE_TEXTS[level - 1](budget)
            )
        else:
            return

        await self.registry.set_text_replies(level >= LISTEN)
        if level >= STOP:
            # Not awaited: this may run inside a voice bridge's own tick,
            # which leaving voice cancels.
            self._spawn(self._stop_for_limit())
        else:
            self._spawn(self._sync_all_voice())

    def _first_text_channel(self):
        for link in self.links():
            channel = self.client.get_channel(link.text_channel_id)
            if channel is not None:
                return channel
        return None

    async def _stop_for_limit(self) -> None:
        for link in self.links():
            await self.leave_voice(link)
        for conversation_id in list(self.registry.sessions):
            await self.registry.close(conversation_id, wait=RESTART_WAIT_SECONDS)

    async def voice_active(self, link: Link) -> bool:
        """False out of voice (text only, or stopped): the bridge sends nothing."""

        return not (self.notices.is_active(TEXT_ONLY) or self.notices.is_active(LIMIT))

    async def server_reachable(self, channel, reachable: bool) -> None:
        if reachable:
            await self.notices.resolve(OFFLINE, messages.BACK_ONLINE)
        else:
            await self.notices.raise_(OFFLINE, channel, messages.OFFLINE)

    def _on_reply(self, session: ScopeSession, is_final: bool) -> None:
        if is_final:
            self.notices.forget(TURN_FAILED)

    async def _on_server_error(self, session: ScopeSession, message: str) -> None:
        await self.notices.raise_(TURN_FAILED, session.replies.channel, messages.TURN_FAILED)

    async def _on_usage(self, session: ScopeSession, usage: dict) -> None:
        self.usage.record(self.user_id, usage)
        await self.apply_stage(session.replies.channel)

    async def recheck_limits(self) -> None:
        """After a new day, week or month, or a changed limit."""

        await self.apply_stage()

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
            runtime.coordinator_chat = getattr(self, "coordinator_chat", None)
            if runtime.coordinator_chat is not None and hasattr(runtime.coordinator_chat, "warm_up"):
                # Its linked channels listen from the start (coordinator/bridge.py warm_up).
                runtime.after_ready.append(runtime.coordinator_chat.warm_up)
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
