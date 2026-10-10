"""
Restarting, pausing and inspecting a bot -- what /restart and /mulca do --
without Discord or a MUCA-Server: the session registry's per-scope locking
and backoff, the voice bridge after a reopen, BotRuntime/BotManager, and the
commands' replies.
"""

import asyncio
import time

import pytest

import mulca_discord.sessions as sessions_module
from mulca_discord import messages
from dataclasses import replace

import discord

from mulca_discord.commands import (
    DIARY_FORM_URL,
    DIARY_MESSAGE,
    HELP_MESSAGE,
    announce_intro,
    announce_intro_everywhere,
    control,
    format_status,
    format_usage,
    greet_first_session,
    greet_first_session_everywhere,
    link_channels,
    post_help_everywhere,
    restart_message,
    send_long,
    set_dms,
    set_mode,
    set_model,
    split_message,
    unlink_channel,
)
from mulca_discord.links import Link, LinkStore
from mulca_discord.runtime import (
    DMS_OFF_REPLY,
    AmbiguousBotName,
    BotManager,
    BotRuntime,
    RestartOutcome,
)
from mulca_discord.sessions import Scope, SessionRegistry
from mulca_discord.voice.bridge import VoiceBridge

GUILD = 900
ALPHA = Link(text_channel_id=111, guild_id=GUILD, bot_id=1, voice_channel_id=222)


# ----------------------------------------------------------------------
# SessionRegistry
# ----------------------------------------------------------------------


class FakeMucaClient:
    instances: list["FakeMucaClient"] = []

    def __init__(self, url, *, conversation_id, is_dm, linked_conversation_id=None, **models):
        self.conversation_id = conversation_id
        self.is_open = False
        self.close_code = None
        self.release = asyncio.Event()
        self.release.set()
        self.closes: list[float | None] = []
        FakeMucaClient.instances.append(self)

    async def connect(self) -> None:
        self.is_open = True

    async def close(self, *, wait_for_server=None) -> bool:
        self.closes.append(wait_for_server)
        await self.release.wait()
        self.is_open = False
        return True


@pytest.fixture
def registry():
    FakeMucaClient.instances = []
    return SessionRegistry("ws://unused/", client_factory=FakeMucaClient)


async def open_scope(registry, conversation_id):
    return await registry.get(Scope(conversation_id=conversation_id), reply_channel=None)


async def test_a_restart_waits_for_the_server_and_holds_only_its_own_scope(registry):
    restarted = await open_scope(registry, "instance:a")
    await open_scope(registry, "instance:b")
    restarted.client.release.clear()

    restart = asyncio.create_task(registry.restart("instance:a"))
    await asyncio.sleep(0.01)

    # Another scope isn't held up by the restart...
    await asyncio.wait_for(open_scope(registry, "instance:b"), timeout=0.5)

    # ...but the restarted one can't reopen before the server confirmed.
    reopen = asyncio.create_task(open_scope(registry, "instance:a"))
    await asyncio.sleep(0.05)
    assert not reopen.done()

    restarted.client.release.set()
    assert await restart
    fresh = await reopen

    assert restarted.client.closes == [sessions_module.RESTART_WAIT_SECONDS]
    assert fresh.client is not restarted.client


async def test_a_session_that_keeps_dying_young_is_reopened_ever_more_slowly(
    registry,
    monkeypatch,
):
    monkeypatch.setattr(sessions_module, "SHORT_LIVED_BACKOFF_SECONDS", (0.01, 0.03))
    scope = "instance:a"

    delays = []
    for _ in range(3):
        session = await open_scope(registry, scope)
        session.client.is_open = False  # the server ended it at once
        started = time.monotonic()
        await open_scope(registry, scope)
        delays.append(time.monotonic() - started)
        registry.find(scope).client.is_open = False

    assert registry._backoff[scope] == 0.03
    assert delays[0] >= 0.01 and delays[2] >= 0.03

    # A session that lived long enough resets the backoff.
    registry.find(scope).opened_at -= sessions_module.SHORT_LIVED_SECONDS
    await open_scope(registry, scope)
    assert scope not in registry._backoff


# ----------------------------------------------------------------------
# Voice after a reopen
# ----------------------------------------------------------------------


class RosterClient:
    def __init__(self) -> None:
        self.rosters: list[dict] = []

    async def send_audio_stream(self, **frame) -> None:
        pass

    async def send_participants(self, roster, *, modality: str = "text") -> None:
        self.rosters.append(roster)


class ReopeningRegistry:
    """Hands out a new session (client) whenever `reopen` is called."""

    def __init__(self) -> None:
        self.reopen()

    def reopen(self) -> None:
        class Session:
            on_state_update = None

        self.session = Session()
        self.session.client = RosterClient()

    async def run(self, scope, action, **kwargs):
        await action(self.session.client)
        return self.session


class SilentVoiceClient:
    def listen(self, sink) -> None:
        pass

    def is_connected(self) -> bool:
        return True

    def is_playing(self) -> bool:
        return False

    def stop(self) -> None:
        pass


async def test_a_reopened_voice_session_gets_the_roster_again():
    registry = ReopeningRegistry()
    bridge = VoiceBridge(
        scope=Scope(conversation_id="instance:team-alpha"),
        registry=registry,
        voice_client=SilentVoiceClient(),
        reply_channel=None,
        roster=lambda: {1: "Ada"},
    )
    await bridge._tick()
    bridge.player.enqueue(b"\x00\x00\x00\x00" * 4800)  # 200 ms still to say
    assert bridge.player.is_notifying()

    registry.reopen()
    await bridge._tick()

    assert registry.session.client.rosters == [{1: "Ada"}]
    # What the old session still had queued is dropped, not played.
    assert not bridge.player.is_notifying()


# ----------------------------------------------------------------------
# BotRuntime / BotManager
# ----------------------------------------------------------------------


class Permissions:
    def __init__(self, allowed: set[str]) -> None:
        self._allowed = allowed

    def __getattr__(self, name: str) -> bool:
        return name in self._allowed


ALL_PERMISSIONS = {
    "view_channel",
    "send_messages",
    "read_message_history",
    "connect",
    "speak",
    "use_voice_activation",
}


class FakeMember:
    def __init__(self, id: int, name: str = "member", bot: bool = False) -> None:
        self.id = id
        self.display_name = name
        self.bot = bot


class FakeGuild:
    def __init__(self, id: int = GUILD) -> None:
        self.id = id
        self.members: dict[int, FakeMember] = {}
        self.me = None

    def get_member(self, user_id):
        return self.members.get(user_id)


class FakeTyping:
    """discord.py's typing() is an async context manager; this records
    whether it was ever entered, nothing else -- no actual re-triggering
    loop to fake."""

    def __init__(self, channel: "FakeChannel") -> None:
        self._channel = channel

    async def __aenter__(self):
        self._channel.typing_entered += 1
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None


class FakeMessage:
    """Enough of discord.Message for _replace_greeting's delete-then-post."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.deleted = False

    async def delete(self) -> None:
        self.deleted = True


class FakeChannel:
    """A channel, and what each member may do in it."""

    def __init__(self, id: int, guild: FakeGuild, members=(), name: str = "") -> None:
        self.id = id
        self.guild = guild
        self.name = name
        self.members = list(members)
        self.allowed: dict[int, set[str]] = {}
        self.typing_entered = 0
        self.sent: list[str] = []
        self.sent_messages: list[FakeMessage] = []
        # Simulates a channel whose .send() fails for its own reason (found
        # live: a channel that otherwise worked for normal replies, but
        # whose link.text_channel_id apparently didn't -- the admin
        # commands used to just say "Posted" regardless, hiding it).
        self.send_fails_with: Exception | None = None

    def permissions_for(self, member):
        return Permissions(self.allowed.get(member.id, ALL_PERMISSIONS))

    def typing(self) -> FakeTyping:
        return FakeTyping(self)

    async def send(self, content) -> FakeMessage:
        if self.send_fails_with is not None:
            raise self.send_fails_with
        self.sent.append(content)
        message = FakeMessage(content)
        self.sent_messages.append(message)
        return message


class FakeUser:
    def __init__(self, name: str, id: int) -> None:
        self.name = name
        self.id = id


class FakeDiscordClient:
    def __init__(self, name="MULCA", id=1, guilds=(GUILD,)) -> None:
        self.user = FakeUser(name, id)
        self.latency = 0.042
        self.guilds = {guild_id: FakeGuild(guild_id) for guild_id in guilds}
        for guild in self.guilds.values():
            guild.members[id] = guild.me = FakeMember(id, name, bot=True)
        self.channels: dict[int, FakeChannel] = {}

    def add_channel(
        self, id: int, guild_id: int = GUILD, members=(), name: str = ""
    ) -> FakeChannel:
        channel = FakeChannel(id, self.guilds[guild_id], members, name=name)
        for member in members:
            channel.guild.members[member.id] = member
        self.channels[id] = channel
        return channel

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    def get_guild(self, guild_id):
        return self.guilds.get(guild_id)

    def is_ready(self) -> bool:
        return True


class FakeRegistry:
    def __init__(self) -> None:
        self.sessions: dict = {}
        self.restarted: list[str] = []
        self.closed: list[tuple[str, float | None]] = []
        self.scopes: list[Scope] = []
        self.text_replies = False

    async def set_text_replies(self, text_replies: bool) -> None:
        self.text_replies = text_replies

    async def restart(self, conversation_id, wait=5.0) -> bool:
        self.restarted.append(conversation_id)
        return True

    async def close(self, conversation_id, *, wait=None) -> bool:
        self.closed.append((conversation_id, wait))
        self.sessions.pop(conversation_id, None)
        return True

    def find(self, conversation_id):
        return self.sessions.get(conversation_id)

    async def run(self, scope, action, **kwargs):
        self.scopes.append(scope)


class FakeBridge:
    def __init__(self) -> None:
        self.roster_updates = 0
        self.disconnected = False

    async def update_participants(self) -> None:
        self.roster_updates += 1

    async def disconnect(self) -> None:
        self.disconnected = True


def make_runtime(store=None, *, link=ALPHA, **client_kwargs) -> BotRuntime:
    store = store or LinkStore(":memory:")
    runtime = BotRuntime(
        client=FakeDiscordClient(**client_kwargs),
        registry=FakeRegistry(),
        store=store,
    )
    if link is not None:
        store.save(link)
    return runtime


def _age_greeting(runtime: BotRuntime, conversation_id: str, days: float) -> None:
    """Pushes a conversation's persisted cooldown clock back, for tests."""

    last_greeted_at, had_a_session = runtime.store.greeting_state(conversation_id)
    runtime.store.set_greeting_state(
        conversation_id,
        last_greeted_at=last_greeted_at - days * 86400,
        had_a_session=had_a_session,
    )


def message(author_id: int, channel, content: str = "hello", *, name: str = "Ada"):
    class Message:
        pass

    msg = Message()
    msg.author = FakeMember(author_id, name)
    msg.channel = channel
    msg.content = content
    return msg


async def test_restarting_a_link_already_in_voice_does_a_full_rejoin():
    # Found live: running /restart while already in voice left the voice
    # connection itself untouched, only silently refreshing its roster
    # (update_participants() alone) -- not an actual fresh reconnect, just
    # a no-op from the user's perspective. Now it leaves and rejoins for
    # real, same full reset the watchdog's own recovery path uses.
    runtime = make_runtime()
    bridge = runtime.voice[ALPHA.name] = FakeBridge()
    rejoined = []

    async def join_voice(link):
        rejoined.append(link)

    runtime.join_voice = join_voice

    outcome = await runtime.restart_link(ALPHA)

    assert outcome == RestartOutcome(link=ALPHA, confirmed=True)
    assert runtime.registry.restarted == ["channel:111"]
    assert bridge.disconnected
    assert rejoined == [ALPHA]


async def test_restarting_a_link_rejoins_voice_if_it_had_left():
    # Found live: /restart on a link whose bot wasn't currently in voice
    # (it had left because the channel was empty, or never joined) did
    # nothing for voice at all -- update_participants() only ever refreshed
    # an *already* joined bridge's roster.
    runtime = make_runtime()
    runtime.client.add_channel(
        ALPHA.voice_channel_id, members=[FakeMember(5, "Ada")],
    )
    joined = []

    async def join_voice(link):
        joined.append(link)

    runtime.join_voice = join_voice
    assert ALPHA.name not in runtime.voice

    await runtime.restart_link(ALPHA)

    assert joined == [ALPHA]


async def test_restarting_a_link_with_nobody_in_an_empty_voice_channel_stays_out():
    # Restarting shouldn't make it join an empty channel just because
    # nobody's there is unrelated to whether the session itself restarted.
    runtime = make_runtime()
    runtime.client.add_channel(ALPHA.voice_channel_id, members=[])
    joined = []

    async def join_voice(link):
        joined.append(link)

    runtime.join_voice = join_voice

    await runtime.restart_link(ALPHA)

    assert joined == []
    assert ALPHA.name not in runtime.voice


async def test_a_paused_bot_leaves_voice_closes_sessions_and_ignores_messages():
    runtime = make_runtime()
    text = runtime.client.add_channel(111)
    bridge = runtime.voice[ALPHA.name] = FakeBridge()
    runtime.registry.sessions = {"channel:111": object(), "dm:5": object()}

    await runtime.pause()
    await runtime.on_message(message(5, text))

    assert bridge.disconnected
    assert runtime.voice == {}
    assert {closed for closed, _ in runtime.registry.closed} == {"channel:111", "dm:5"}
    assert runtime.registry.scopes == []


async def test_stop_survives_a_restart_of_the_bot():
    store = LinkStore(":memory:")
    first = make_runtime(store)
    store.register_bot(1, "MULCA", is_primary=True)
    await first.pause()

    second = make_runtime(store, link=None)
    await second.on_ready()

    assert second.paused


async def test_a_message_in_a_linked_channel_goes_to_its_memory_and_is_remembered():
    runtime = make_runtime()
    text = runtime.client.add_channel(111, members=[FakeMember(5, "Ada")])

    await runtime.on_message(message(5, text))

    [scope] = runtime.registry.scopes
    assert scope.conversation_id == "channel:111"
    assert runtime.store.last_link_for(5) == ALPHA


async def test_the_scope_carries_the_channels_own_name():
    # aui.main_instructions() uses this to tell a team's own MULCA which
    # tutoring cohort it belongs to -- found live, without it every
    # channel got every cohort's deadline listed together, with nothing
    # saying which one was actually this channel's own.
    runtime = make_runtime()
    text = runtime.client.add_channel(111, members=[FakeMember(5, "Ada")], name="group-10")

    await runtime.on_message(message(5, text))

    [scope] = runtime.registry.scopes
    assert scope.channel_name == "group-10"


async def test_the_first_real_message_starts_the_cooldown_without_a_greeting():
    # Found live: an admin's own test messages used to count as the
    # group's "first message," making the reminder fire the moment real
    # participants started talking. The first qualifying message now only
    # starts the cooldown clock -- the reminder itself doesn't show until
    # GREETING_COOLDOWN_SECONDS has actually passed since.
    runtime = make_runtime()
    text = runtime.client.add_channel(111, members=[FakeMember(5, "Ada")])

    await runtime.on_message(message(5, text))

    assert text.sent == []

    # A day later -- still inside the two-day cooldown.
    _age_greeting(runtime, "channel:111", days=1)
    await runtime.on_message(message(5, text))

    assert text.sent == []

    # A full two days after the first message -- due now. No real session
    # has happened yet, so this is FIRST_SESSION_MESSAGE, not "Welcome
    # back!".
    _age_greeting(runtime, "channel:111", days=1.01)
    await runtime.on_message(message(5, text))

    assert text.sent == [messages.FIRST_SESSION_MESSAGE]


async def test_the_reminder_does_not_repeat_within_two_days():
    runtime = make_runtime()
    text = runtime.client.add_channel(111, members=[FakeMember(5, "Ada")])

    await runtime.on_message(message(5, text))  # starts the clock, no post
    _age_greeting(runtime, "channel:111", days=2)
    await runtime.on_message(message(5, text))  # first reminder

    assert len(text.sent) == 1
    first_greeting = text.sent_messages[0]

    # A day later -- still within two days of the reminder itself (not
    # the original first message), so no repeat yet.
    _age_greeting(runtime, "channel:111", days=1)
    await runtime.on_message(message(5, text))

    assert len(text.sent) == 1

    # A further two days -- due again, and now a real "Welcome back!",
    # since a reminder (and so a real session) already happened. The
    # previous one is deleted rather than left to pile up.
    _age_greeting(runtime, "channel:111", days=2)
    await runtime.on_message(message(5, text))

    assert len(text.sent) == 2
    assert text.sent[1] == messages.DAILY_GREETING
    assert first_greeting.deleted


async def test_excluded_test_accounts_never_start_the_cooldown_or_get_greeted():
    # GREETING_EXCLUDED_AUTHOR_NAMES: test/admin accounts used while
    # setting a channel up, not real participants -- their messages don't
    # count at all for this, no matter how many or how old.
    runtime = make_runtime()
    text = runtime.client.add_channel(
        111,
        members=[FakeMember(5, "Ada"), FakeMember(6, "Admin"), FakeMember(7, "Mats")],
    )

    await runtime.on_message(message(6, text, "testing one", name="Admin"))
    await runtime.on_message(message(7, text, "testing two", name="mats"))  # case-insensitive
    await runtime.on_message(message(6, text, "still testing", name="Admin"))

    assert text.sent == []
    assert runtime.store.greeting_state("channel:111") == (0.0, False)

    # A real participant's own first message is what actually starts the
    # clock.
    await runtime.on_message(message(5, text))
    _age_greeting(runtime, "channel:111", days=2)
    await runtime.on_message(message(5, text))

    assert text.sent == [messages.FIRST_SESSION_MESSAGE]


async def test_a_restart_does_not_undo_todays_greeting():
    # Found live: /mulca greet ran, then the bot process restarted before
    # the channel's real first message arrived later the same day -- with
    # the greeted state kept in memory only, that restart reset it, and
    # the reminder posted a second time. greeting_state lives in the
    # store (SQLite), so a new BotRuntime sharing the same store (what a
    # restart actually looks like -- the store is the one thing that
    # survives it) must still remember it was already greeted today.
    store = LinkStore(":memory:")
    first_process = make_runtime(store=store)
    manager = BotManager([first_process])
    text = first_process.client.add_channel(111, members=[FakeMember(5, "Ada")])

    await greet_first_session(manager, text)

    # Simulates a restart: a fresh BotRuntime (so none of its in-memory
    # state carries over), the same persisted store.
    second_process = make_runtime(store=store, link=None)
    second_process.client.channels[111] = text
    text.sent.clear()

    await second_process.on_message(message(5, text))

    assert text.sent == []


def test_the_daily_greeting_is_conditional_not_an_instruction():
    # Not everyone opens Discord every day just to work on the project --
    # the reminder shouldn't read as though it assumes they are.
    assert "if you get" in messages.DAILY_GREETING.lower()
    assert messages.SESSION_REMINDER in messages.DAILY_GREETING


def test_the_session_reminder_offers_help_with_the_tasks_lifecycle():
    # Both FIRST_SESSION_MESSAGE and DAILY_GREETING share this -- a quick
    # capability reminder so people know to ask MULCA for help planning,
    # not just moderating.
    assert "planning, performing, and reporting" in messages.SESSION_REMINDER
    assert "planning, performing, and reporting" in messages.FIRST_SESSION_MESSAGE
    assert "planning, performing, and reporting" in messages.DAILY_GREETING


async def test_greet_posts_the_first_session_variant_and_skips_todays_daily_one():
    runtime = make_runtime()
    manager = BotManager([runtime])
    text = runtime.client.add_channel(111, members=[FakeMember(5, "Ada")])

    reply = await greet_first_session(manager, text)

    assert "Posted" in reply
    assert text.sent == [messages.FIRST_SESSION_MESSAGE]
    assert "Welcome back" not in messages.FIRST_SESSION_MESSAGE

    # The channel's first real message of the same day doesn't also get
    # the regular daily greeting -- /mulca greet already covered today.
    await runtime.on_message(message(5, text))

    assert text.sent == [messages.FIRST_SESSION_MESSAGE]


async def test_a_greeting_run_days_before_the_first_message_still_isnt_a_welcome_back():
    # /mulca greet 3 days before anyone actually says anything -- the
    # group's first real message, well past the cooldown by the time it
    # arrives, is still their first session: it must not say "Welcome
    # back!" just because the cooldown has long since elapsed.
    runtime = make_runtime()
    manager = BotManager([runtime])
    text = runtime.client.add_channel(111, members=[FakeMember(5, "Ada")])

    await greet_first_session(manager, text)
    _age_greeting(runtime, "channel:111", days=3)

    await runtime.on_message(message(5, text))

    assert text.sent == [messages.FIRST_SESSION_MESSAGE, messages.FIRST_SESSION_MESSAGE]

    # Only now has a real session actually happened -- two more days gets
    # the usual "Welcome back!".
    _age_greeting(runtime, "channel:111", days=2)
    await runtime.on_message(message(5, text))

    assert text.sent[2] == messages.DAILY_GREETING


async def test_greet_refuses_an_unlinked_channel():
    runtime = make_runtime(link=None)
    manager = BotManager([runtime])
    text = runtime.client.add_channel(999)

    reply = await greet_first_session(manager, text)

    assert "doesn't serve" in reply
    assert text.sent == []


class FakeMucaClientForTyping:
    def __init__(self) -> None:
        self.on_assistant_text = None
        self.sent_texts: list[str] = []

    async def send_participants(self, roster, *, modality) -> None:
        pass

    async def send_user_text(self, *, speaker, speaker_name, text) -> None:
        self.sent_texts.append(text)


async def test_sending_a_message_shows_typing_until_the_first_reply_piece():
    # Found live: a web-search-backed reply can take several seconds with
    # nothing else visible meanwhile.
    runtime = make_runtime()
    text = runtime.client.add_channel(111, members=[FakeMember(5, "Ada")])
    fake_client = FakeMucaClientForTyping()

    received = []

    async def real_handler(reply_text, is_final, modality) -> None:
        received.append((reply_text, is_final, modality))

    fake_client.on_assistant_text = real_handler

    async def run(scope, action, **kwargs):
        runtime.registry.scopes.append(scope)
        await action(fake_client)

    runtime.registry.run = run

    await runtime.on_message(message(5, text))
    await asyncio.sleep(0)  # let the background typing task start

    assert text.typing_entered == 1
    assert fake_client.sent_texts == ["hello"]

    # The real reply arrives -- the wrapper forwards it, then gets out of
    # the way for every later delta of the same reply.
    await fake_client.on_assistant_text("Hi there!", False, "text")

    assert received == [("Hi there!", False, "text")]
    assert fake_client.on_assistant_text is real_handler


async def test_a_message_in_an_unlinked_channel_is_ignored():
    runtime = make_runtime()
    other = runtime.client.add_channel(999)

    await runtime.on_message(message(5, other))

    assert runtime.registry.scopes == []


class FakeDMChannel(discord.DMChannel):
    """Passes isinstance(..., discord.DMChannel); records what's sent."""

    def __init__(self) -> None:
        self.id = 77
        self.sent: list[str] = []

    async def send(self, content):
        self.sent.append(content)


async def test_dms_are_off_by_default():
    runtime = make_runtime()
    runtime.client.add_channel(111, members=[FakeMember(5, "Ada")])
    dm = FakeDMChannel()

    await runtime.on_message(message(5, dm))

    assert dm.sent == [DMS_OFF_REPLY]
    assert runtime.registry.scopes == []


async def test_with_dms_on_people_who_see_the_channel_may_dm_and_it_remembers():
    runtime = make_runtime(link=replace(ALPHA, allow_dms=True))
    runtime.client.add_channel(111, members=[FakeMember(5, "Ada")])
    dm = FakeDMChannel()

    await runtime.on_message(message(5, dm))

    [scope] = runtime.registry.scopes
    assert scope.conversation_id == "dm:5"
    assert scope.is_dm and scope.linked_conversation_id == "channel:111"
    assert dm.sent == []


async def test_with_dms_on_people_who_cant_see_the_channel_still_cant_dm():
    runtime = make_runtime(link=replace(ALPHA, allow_dms=True))
    text = runtime.client.add_channel(111, members=[FakeMember(5, "Ada")])
    text.allowed[5] = set()
    # In the server, but the channel is private to others.
    runtime.client.guilds[GUILD].members[6] = FakeMember(6, "Bob")
    text.allowed[6] = set()
    dm = FakeDMChannel()

    await runtime.on_message(message(5, dm))
    await runtime.on_message(message(6, dm))
    # Not in the server at all.
    await runtime.on_message(message(7, dm))

    assert dm.sent == [DMS_OFF_REPLY, DMS_OFF_REPLY, DMS_OFF_REPLY]
    assert runtime.registry.scopes == []


def test_a_dm_reads_the_dm_enabled_channel_its_sender_last_spoke_in():
    store = LinkStore(":memory:")
    runtime = make_runtime(store, link=replace(ALPHA, allow_dms=True))
    other = Link(text_channel_id=333, guild_id=GUILD, bot_id=1, allow_dms=True)
    closed = Link(text_channel_id=555, guild_id=GUILD, bot_id=1)
    store.save(other)
    store.save(closed)
    for channel_id in (111, 333, 555):
        runtime.client.add_channel(channel_id, members=[FakeMember(5, "Ada")])

    store.remember_speaker(5, 333)
    assert runtime.dm_link(5) == other

    # Last spoke in a channel without DMs: the first DM-enabled one instead.
    store.remember_speaker(5, 555)
    assert runtime.dm_link(5) == replace(ALPHA, allow_dms=True)


def test_status_reports_each_link_in_the_server():
    runtime = make_runtime()

    status = runtime.status(GUILD)

    assert status.name == "MULCA"
    assert status.online and not status.paused
    assert status.latency_ms == pytest.approx(42)
    [link] = status.links
    assert link.text_channel_id == 111
    assert not link.session_open
    assert "can't see channel 111" in link.problems

    assert runtime.status(guild_id=901).links == ()


def test_the_manager_finds_the_bot_serving_a_channel_and_resolves_targets():
    store = LinkStore(":memory:")
    alpha = make_runtime(store, name="MULCA", id=1, guilds=(GUILD,))
    beta = make_runtime(
        store,
        link=Link(text_channel_id=333, guild_id=GUILD, bot_id=2, voice_channel_id=444),
        name="MULCA 2",
        id=2,
        guilds=(GUILD, 901),
    )
    manager = BotManager([alpha, beta])

    assert manager.link_for_channel(444)[0] is beta
    assert manager.link_for_channel(111)[0] is alpha
    assert manager.link_for_channel(999) is None
    assert manager.resolve("all", GUILD) == [alpha, beta]
    assert manager.resolve(None, 901) == [beta]
    assert manager.resolve("mulca 2", GUILD) == [beta]
    assert manager.resolve("2", GUILD) == [beta]
    # Never a bot outside the server the command came from.
    assert manager.resolve("MULCA", 901) == []


def test_resolving_an_ambiguous_name_raises_instead_of_guessing():
    """
    Two bots running from the same code share a Discord username until
    someone renames one -- found live: /mulca link's `chosen[0]` would
    otherwise silently link whichever bot happened to resolve first.
    """

    store = LinkStore(":memory:")
    alpha = make_runtime(store, name="MULCA", id=1, guilds=(GUILD,))
    twin = make_runtime(store, link=None, name="MULCA", id=3, guilds=(GUILD,))
    manager = BotManager([alpha, twin])

    with pytest.raises(AmbiguousBotName):
        manager.resolve("MULCA", GUILD)

    # The id is always unique, so it's never ambiguous even when the name is.
    assert manager.resolve("1", GUILD) == [alpha]
    assert manager.resolve("3", GUILD) == [twin]


async def test_control_reports_an_ambiguous_name_instead_of_guessing():
    store = LinkStore(":memory:")
    alpha = make_runtime(store, name="MULCA", id=1, guilds=(GUILD,))
    twin = make_runtime(store, link=None, name="MULCA", id=3, guilds=(GUILD,))
    manager = BotManager([alpha, twin])

    reply = await control(manager, "restart", "MULCA", GUILD)

    assert "1" in reply and "3" in reply


# ----------------------------------------------------------------------
# /mulca link and /mulca unlink
# ----------------------------------------------------------------------


async def test_linking_saves_the_link_and_joins_voice_if_someone_is_there():
    runtime = make_runtime(link=None)
    text = runtime.client.add_channel(111)
    voice = runtime.client.add_channel(222, members=[FakeMember(5, "Ada")])
    joined = []

    async def join_voice(link):
        joined.append(link)

    runtime.join_voice = join_voice

    reply = await link_channels(
        bot=runtime,
        guild_id=GUILD,
        text_channel=text,
        voice_channel=voice,
        created_by=5,
    )

    assert "Linked" in reply
    assert runtime.links() == [ALPHA]
    assert joined == [ALPHA]
    # A brand-new link -- greet the group once, right away.
    assert text.sent == [messages.INTRO_MESSAGE]


async def test_linking_posts_the_intro_through_the_linked_bots_own_client():
    # text_channel, same as /mulca announce's channel parameter, comes from
    # the slash command's own interaction -- always the primary bot's
    # connection, regardless of which bot account `bot:` actually targets.
    primary = make_runtime(link=None, name="MULCA-parent", id=1)
    serving_bot = make_runtime(store=primary.store, link=None, name="mulca-10", id=2)

    from_primary = primary.client.add_channel(111)
    from_primary.send_fails_with = RuntimeError("403 Forbidden (Missing Access)")
    from_serving_bot = serving_bot.client.add_channel(111)

    reply = await link_channels(
        bot=serving_bot,
        guild_id=GUILD,
        text_channel=from_primary,
        created_by=5,
    )

    assert "Linked" in reply
    assert from_serving_bot.sent == [messages.INTRO_MESSAGE]
    assert from_primary.sent == []


async def test_linking_a_linked_channel_again_updates_it():
    runtime = make_runtime()
    text = runtime.client.add_channel(111)

    reply = await link_channels(bot=runtime, guild_id=GUILD, text_channel=text)

    assert "Updated" in reply
    assert runtime.links() == [Link(text_channel_id=111, guild_id=GUILD, bot_id=1)]
    # Not a new link -- no repeat of the intro message for a settings tweak.
    assert text.sent == []


async def test_announce_reposts_the_intro_in_an_already_linked_channel():
    # For channels linked before the message existed, or any time it's
    # worth sending again -- unlike link_channels' own auto-post, which
    # only fires once, on a brand-new link.
    runtime = make_runtime()
    manager = BotManager([runtime])
    text = runtime.client.add_channel(111)

    reply = await announce_intro(manager, text)

    assert "Posted" in reply
    assert text.sent == [messages.INTRO_MESSAGE]


async def test_announce_posts_through_the_serving_bots_own_client_not_the_primarys():
    # Found live: a private channel linked to one specific bot account in a
    # multi-bot deployment (one account per simultaneous voice channel) --
    # MULCA replied there fine conversationally (that always goes out
    # through the serving bot's own live message event), but /mulca
    # announce, run through the primary bot's slash command, 403'd
    # (Missing Access) by sending through the *primary* bot's own
    # connection instead, which was never added to that private channel at
    # all. Same channel ID, two different bot accounts, two different
    # actual Discord channel objects.
    primary = make_runtime(link=None, name="MULCA-parent", id=1)
    serving_bot = make_runtime(link=None, name="mulca-10", id=2)
    manager = BotManager([primary, serving_bot])

    # What the primary bot's own interaction would hand the command --
    # it was never added to this private channel.
    from_primary = primary.client.add_channel(111)
    from_primary.send_fails_with = RuntimeError("403 Forbidden (Missing Access)")

    # The same channel id, through the bot that's actually linked to it.
    from_serving_bot = serving_bot.client.add_channel(111)
    serving_bot.store.save(Link(text_channel_id=111, guild_id=GUILD, bot_id=2))

    reply = await announce_intro(manager, from_primary)

    assert "Posted" in reply
    assert from_serving_bot.sent == [messages.INTRO_MESSAGE]
    assert from_primary.sent == []


async def test_announce_help_and_greet_all_post_to_every_linked_channel_in_the_server():
    # Setup sequence across a whole server: announce, then help, then
    # greet, each asked once with all=true instead of one /mulca call per
    # channel.
    runtime = make_runtime(guilds=(GUILD, 9999))
    manager = BotManager([runtime])
    first = runtime.client.add_channel(111)  # ALPHA, already linked
    second = runtime.client.add_channel(333)
    runtime.store.save(Link(text_channel_id=333, guild_id=GUILD, bot_id=1))
    other_server = runtime.client.add_channel(444, guild_id=9999)
    runtime.store.save(Link(text_channel_id=444, guild_id=9999, bot_id=1))

    announce_reply = await announce_intro_everywhere(manager, GUILD)
    help_reply = await post_help_everywhere(manager, GUILD)
    greet_reply = await greet_first_session_everywhere(manager, GUILD)

    for reply in (announce_reply, help_reply, greet_reply):
        assert "<#111>" in reply and "<#333>" in reply and "<#444>" not in reply

    assert first.sent == [messages.INTRO_MESSAGE, HELP_MESSAGE, messages.FIRST_SESSION_MESSAGE]
    assert second.sent == [messages.INTRO_MESSAGE, HELP_MESSAGE, messages.FIRST_SESSION_MESSAGE]
    # A different server's own linked channel is untouched.
    assert other_server.sent == []


async def test_announce_all_with_no_linked_channel_says_so():
    runtime = make_runtime(link=None)
    manager = BotManager([runtime])

    assert "No linked channel" in await announce_intro_everywhere(manager, GUILD)


async def test_announce_reports_a_failed_post_instead_of_lying_about_it():
    # Found live: a specific channel's own link failed to receive it
    # (MULCA still replied there normally otherwise), but the command said
    # "Posted" regardless -- channel.send()'s own exception was silently
    # swallowed and never reached the admin's reply.
    runtime = make_runtime()
    manager = BotManager([runtime])
    text = runtime.client.add_channel(111)
    text.send_fails_with = RuntimeError("403 Forbidden")

    reply = await announce_intro(manager, text)

    assert "Posted" not in reply
    assert "Could not post" in reply and "403 Forbidden" in reply
    assert text.sent == []


async def test_announce_all_reports_per_channel_which_ones_failed():
    runtime = make_runtime()
    manager = BotManager([runtime])
    working = runtime.client.add_channel(111)
    broken = runtime.client.add_channel(333)
    runtime.store.save(Link(text_channel_id=333, guild_id=GUILD, bot_id=1))
    broken.send_fails_with = RuntimeError("403 Forbidden")

    reply = await announce_intro_everywhere(manager, GUILD)

    assert "Posted in: <#111>." in reply
    assert "Could not post in: <#333> (403 Forbidden)." in reply
    assert working.sent == [messages.INTRO_MESSAGE]
    assert broken.sent == []


async def test_greet_reports_a_failed_post_and_doesnt_start_the_cooldown():
    # A failed post shouldn't also block on_message's own later retry via
    # the automatic reminder.
    runtime = make_runtime()
    manager = BotManager([runtime])
    text = runtime.client.add_channel(111, members=[FakeMember(5, "Ada")])
    text.send_fails_with = RuntimeError("403 Forbidden")

    reply = await greet_first_session(manager, text)

    assert "Could not post" in reply
    assert runtime.store.greeting_state("channel:111") == (0.0, False)

    text.send_fails_with = None
    await runtime.on_message(message(5, text))  # starts the clock, no post
    _age_greeting(runtime, "channel:111", days=2)
    await runtime.on_message(message(5, text))

    assert text.sent == [messages.FIRST_SESSION_MESSAGE]


async def test_announce_refuses_an_unlinked_channel():
    runtime = make_runtime(link=None)
    manager = BotManager([runtime])
    text = runtime.client.add_channel(999)

    reply = await announce_intro(manager, text)

    assert "doesn't serve" in reply
    assert text.sent == []


async def test_a_bot_that_cant_see_the_channel_is_not_linked():
    runtime = make_runtime(link=None)
    text = runtime.client.add_channel(111)
    text.allowed[1] = set()

    reply = await link_channels(bot=runtime, guild_id=GUILD, text_channel=text)

    assert "can't see" in reply
    assert runtime.links() == []


async def test_a_second_voice_channel_for_the_same_bot_in_one_server_is_refused():
    runtime = make_runtime()
    text = runtime.client.add_channel(333)
    voice = runtime.client.add_channel(444)

    reply = await link_channels(
        bot=runtime,
        guild_id=GUILD,
        text_channel=text,
        voice_channel=voice,
    )

    assert "Not linked" in reply and "one voice channel per server" in reply
    assert runtime.links() == [ALPHA]


async def test_missing_permissions_are_reported_but_the_link_is_made():
    runtime = make_runtime(link=None)
    text = runtime.client.add_channel(111)
    text.allowed[1] = {"view_channel", "read_message_history"}

    reply = await link_channels(bot=runtime, guild_id=GUILD, text_channel=text)

    assert "Linked" in reply
    assert "missing **send_messages**" in reply


async def test_dms_are_turned_on_and_off_per_linked_channel():
    runtime = make_runtime()
    manager = BotManager([runtime])

    on = await set_dms(manager, 222, True)  # by its voice channel, too
    assert "DMs on" in on
    assert runtime.links() == [replace(ALPHA, allow_dms=True)]

    off = await set_dms(manager, 111, False)
    assert "DMs off" in off
    assert runtime.links() == [ALPHA]

    assert "isn't linked" in await set_dms(manager, 999, True)


async def test_turning_dms_off_closes_the_dm_sessions_reading_that_channel(registry):
    runtime = make_runtime(link=replace(ALPHA, allow_dms=True))
    runtime.registry = registry
    reading_alpha = await registry.get(
        Scope("dm:5", is_dm=True, linked_conversation_id=ALPHA.conversation_id),
        reply_channel=None,
    )
    reading_other = await registry.get(
        Scope("dm:6", is_dm=True, linked_conversation_id="channel:999"),
        reply_channel=None,
    )

    await set_dms(BotManager([runtime]), 111, False)

    assert not reading_alpha.client.is_open
    assert reading_other.client.is_open
    await registry.close_all()


async def test_relinking_without_saying_keeps_the_dm_setting():
    runtime = make_runtime(link=replace(ALPHA, allow_dms=True))
    text = runtime.client.add_channel(111)
    voice = runtime.client.add_channel(222)

    await link_channels(bot=runtime, guild_id=GUILD, text_channel=text, voice_channel=voice)
    assert runtime.links()[0].allow_dms

    reply = await link_channels(
        bot=runtime,
        guild_id=GUILD,
        text_channel=text,
        voice_channel=voice,
        allow_dms=False,
    )
    assert not runtime.links()[0].allow_dms
    assert "DMs are off" in reply


async def test_changing_the_mode_on_relink_restarts_the_session():
    runtime = make_runtime()
    text = runtime.client.add_channel(111)
    voice = runtime.client.add_channel(222)

    for _ in range(2):  # the second time, the mode is unchanged
        await link_channels(
            bot=runtime,
            guild_id=GUILD,
            text_channel=text,
            voice_channel=voice,
            listening_mode="wake",
        )

    assert runtime.links()[0].listening_mode == "wake"
    assert runtime.registry.restarted == ["channel:111"]


async def test_mode_switches_every_link_here_and_restarts_only_changed_ones():
    store = LinkStore(":memory:")
    other_guild = Link(text_channel_id=444, guild_id=901, bot_id=1)
    alpha = make_runtime(store, name="MULCA", id=1)
    store.save(other_guild)
    beta = make_runtime(
        store,
        link=Link(text_channel_id=333, guild_id=GUILD, bot_id=2, listening_mode="wake"),
        name="MULCA 2",
        id=2,
    )

    reply = await set_mode(BotManager([alpha, beta]), "wake", None, GUILD)

    assert "<#111>" in reply and "<#333>" not in reply
    assert store.link_for_channel(111).listening_mode == "wake"
    assert store.link_for_channel(444) == other_guild
    assert alpha.registry.restarted == ["channel:111"]
    assert beta.registry.restarted == []
    assert "already" in await set_mode(BotManager([alpha, beta]), "wake", None, GUILD)


async def test_unlinking_closes_the_session_and_forgets_the_link():
    runtime = make_runtime()
    manager = BotManager([runtime])

    reply = await unlink_channel(manager, 222)

    assert "Unlinked" in reply
    assert runtime.links() == []
    assert runtime.registry.closed == [("channel:111", 5.0)]
    assert "isn't linked" in await unlink_channel(manager, 222)


# ----------------------------------------------------------------------
# What the commands say
# ----------------------------------------------------------------------


def test_the_restart_reply_says_whether_the_memory_was_saved():
    saved = restart_message("@Ada", RestartOutcome(ALPHA, confirmed=True))
    unsure = restart_message("@Ada", RestartOutcome(ALPHA, confirmed=False))

    assert "remembers" in saved
    assert "didn't confirm" in unsure


def test_the_help_message_covers_text_voice_and_wake_sessions():
    assert "tutoring assistant" in HELP_MESSAGE
    assert "mention it by name" in HELP_MESSAGE
    assert '"assistant", "MULCA", "bot" or "chatbot"' in HELP_MESSAGE
    # Starting and ending a "wake" voice conversation -- the least
    # self-explanatory of the listening modes, so the one worth spelling
    # out explicitly here.
    assert "get its attention" in HELP_MESSAGE
    assert "bystander mode" in HELP_MESSAGE
    assert "stop" in HELP_MESSAGE and "go to sleep" in HELP_MESSAGE
    # No admin-only commands (/link and friends) belong in member-facing help.
    assert "/mulca link" not in HELP_MESSAGE
    assert "/mulca" not in HELP_MESSAGE


def test_the_diary_message_links_the_form():
    assert DIARY_FORM_URL in DIARY_MESSAGE
    assert "after" in DIARY_MESSAGE
    # A quick nudge for manual feedback, alongside the diary reminder.
    assert "\N{THUMBS UP SIGN}" in DIARY_MESSAGE
    assert "\N{THUMBS DOWN SIGN}" in DIARY_MESSAGE


async def test_control_stops_and_starts_only_the_named_bot():
    store = LinkStore(":memory:")
    alpha = make_runtime(store, name="MULCA", id=1)
    beta = make_runtime(store, link=None, name="MULCA 2", id=2)
    manager = BotManager([alpha, beta])

    stopped = await control(manager, "stop", "MULCA 2", GUILD)
    assert beta.paused and not alpha.paused
    assert "MULCA 2" in stopped

    await control(manager, "start", "all", GUILD)
    assert not beta.paused

    assert "No MULCA bot" in await control(manager, "stop", "nobody", GUILD)


def test_status_text_lists_bots_links_and_problems():
    runtime = make_runtime()

    text = format_status([runtime.status(GUILD)])

    assert "**MULCA**: online" in text
    assert "<#111>" in text and "<#222>" in text
    assert "can't see channel 111" in text
    assert format_status([]) == "No MULCA bot is in this server."


def test_the_primary_bot_registers_restart_and_the_admin_commands():
    import discord

    from mulca_discord.commands import install_commands
    from mulca_discord.discord_client import build_discord_client

    client = build_discord_client(
        muca_server_url="ws://unused/",
        store=LinkStore(":memory:"),
    )
    tree = install_commands(BotManager([client.mulca_runtime]))

    commands = {command.name: command for command in tree.get_commands()}
    assert set(commands) == {"restart", "listen", "help", "diary", "mulca"}
    subcommands = {sub.name: sub for sub in commands["mulca"].commands}
    assert set(subcommands) == {
        "status",
        "restart",
        "stop",
        "start",
        "link",
        "unlink",
        "announce",
        "help",
        "greet",
        "dms",
        "mode",
        "model",
        "costalert",
        "button",
        "bot",
        "limit",
        "usage",
    }
    assert {sub.name for sub in subcommands["bot"].commands} == {"add", "remove", "list"}
    assert {sub.name for sub in subcommands["limit"].commands} == {"set", "clear"}
    # Hidden from everyone without Manage Server, and never in DMs.
    assert commands["mulca"].default_permissions == discord.Permissions(manage_guild=True)
    assert commands["mulca"].guild_only
    assert commands["restart"].guild_only


# ----------------------------------------------------------------------
# /mulca model
# ----------------------------------------------------------------------


def model_manager(*names):
    store = LinkStore(":memory:")
    runtimes = []
    for position, name in enumerate(names, start=1):
        store.register_bot(position, name, is_primary=position == 1)
        runtimes.append(
            make_runtime(
                store,
                link=Link(100 + position, GUILD, position, None),
                name=name,
                id=position,
                guilds=(GUILD,),
            )
        )
    runtimes[0].registry.url = "ws://muca/"
    return BotManager(runtimes, store=store), store, runtimes


async def test_a_bots_own_model_is_saved_and_its_sessions_restart():
    manager, store, runtimes = model_manager("Alpha", "Beta")

    reply = await set_model(manager, " gpt-new ", "Beta", GUILD)

    assert store.models_for(2) == ("gpt-new", "")
    assert store.models_for(1) == ("", "")
    assert runtimes[1].registry.restarted == ["channel:102"]
    assert runtimes[0].registry.restarted == []
    assert "Beta" in reply


async def test_the_intervention_model_changes_only_with_the_flag():
    manager, store, _ = model_manager("Alpha")
    store.set_models(1, "old-main", "old-intervention")

    await set_model(manager, "gpt-new", "Alpha", GUILD)
    assert store.models_for(1) == ("gpt-new", "old-intervention")

    await set_model(manager, "gpt-newer", "Alpha", GUILD, include_intervention=True)
    assert store.models_for(1) == ("gpt-newer", "gpt-newer")


@pytest.mark.parametrize("target", [None, "all"])
async def test_without_a_bot_the_servers_model_changes_and_no_bot_is_touched(target):
    manager, store, runtimes = model_manager("Alpha")
    calls = []

    async def set_server(url, token, model, *, include_intervention):
        calls.append((url, token, model, include_intervention))

    reply = await set_model(
        manager,
        "gpt-new",
        target,
        GUILD,
        include_intervention=True,
        admin_token="secret",
        set_server=set_server,
    )

    assert calls == [("ws://muca/", "secret", "gpt-new", True)]
    assert store.models_for(1) == ("", "")
    assert store.server_models() == ("gpt-new", "gpt-new")
    assert runtimes[0].registry.restarted == []
    assert "MUCA-Server now uses `gpt-new`" in reply


def test_a_long_reply_is_split_between_lines_into_messages_discord_accepts():
    lines = [f"line {i}: " + "x" * (i % 70) for i in range(200)]
    text = "\n".join(lines)

    chunks = split_message(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= 2000 for chunk in chunks)
    assert "\n".join(chunks) == text  # nothing lost, no line cut
    assert split_message("short") == ["short"]


def test_only_an_absurdly_long_line_is_cut_and_order_is_kept():
    text = "before\n" + "x" * 4500 + "\nafter"

    assert split_message(text) == ["before", "x" * 2000, "x" * 2000, "x" * 500 + "\nafter"]


async def test_send_long_sends_every_chunk_ephemerally_and_never_an_empty_one():
    sent = []

    class Followup:
        async def send(self, content, *, ephemeral):
            sent.append((content, ephemeral))

    class Interaction:
        followup = Followup()

    await send_long(Interaction(), "a" * 1500 + "\n\n" + "b" * 1500)
    assert sent == [("a" * 1500 + "\n", True), ("b" * 1500, True)]

    sent.clear()
    await send_long(Interaction(), "")
    assert sent == [("(nothing to show)", True)]


def test_a_status_of_twenty_bots_fits_in_discord_messages():
    store = LinkStore(":memory:")
    bots = []
    for i in range(1, 21):
        store.register_bot(i, f"MULCA-team-{i:02d}", is_primary=i == 1)
        bot = make_runtime(
            store,
            link=Link(1000 + i, GUILD, i, 2000 + i),
            name=f"MULCA-team-{i:02d}",
            id=i,
        )
        bot.client.add_channel(1000 + i)
        bot.client.add_channel(2000 + i)
        bots.append(bot)
    manager = BotManager(bots, store=store)

    text = (
        format_status([bot.status(GUILD) for bot in bots])
        + "\n\nActive use:\n"
        + format_usage(manager, None, GUILD)
    )

    assert len(text) > 2000  # what Discord refused in one message
    assert all(len(chunk) <= 2000 for chunk in split_message(text))


def test_status_shows_each_bots_models_and_where_they_come_from():
    manager, store, runtimes = model_manager("Alpha", "Beta")

    def models_line(runtime):
        return format_status([runtime.status(GUILD)]).splitlines()[1]

    assert models_line(runtimes[0]) == "  models: main server default, intervention server default"

    store.set_server_models("gpt-all")  # main only, as without include_intervention
    store.set_models(2, "gpt-beta")
    assert models_line(runtimes[0]) == "  models: main gpt-all (all bots), intervention server default"
    assert models_line(runtimes[1]) == "  models: main gpt-beta (this bot), intervention server default"

    store.set_server_models("gpt-all-2", "gpt-all-2")
    assert models_line(runtimes[1]) == (
        "  models: main gpt-beta (this bot), intervention gpt-all-2 (all bots)"
    )


async def test_the_servers_model_needs_the_admin_token_and_reports_a_refusal():
    manager, _, _ = model_manager("Alpha")

    async def refuse(*args, **kwargs):
        return "Invalid admin token"

    assert "MUCA_ADMIN_TOKEN" in await set_model(manager, "m", None, GUILD)
    reply = await set_model(
        manager, "m", None, GUILD, admin_token="x", set_server=refuse
    )
    assert "Invalid admin token" in reply


async def test_an_unknown_bot_changes_nothing():
    manager, store, _ = model_manager("Alpha")

    assert "No MULCA bot" in await set_model(manager, "m", "Nobody", GUILD)
    assert store.models_for(1) == ("", "")
