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
from mulca_discord.commands import control, format_status, restart_message
from mulca_discord.instances import MulcaInstance
from mulca_discord.runtime import BotManager, BotRuntime, RestartOutcome
from mulca_discord.sessions import Scope, SessionRegistry
from mulca_discord.voice.bridge import VoiceBridge

ALPHA = MulcaInstance(name="team-alpha", text_channel_id=111, voice_channel_id=222)


# ----------------------------------------------------------------------
# SessionRegistry
# ----------------------------------------------------------------------


class FakeMucaClient:
    instances: list["FakeMucaClient"] = []

    def __init__(self, url, *, conversation_id, is_dm, linked_conversation_id=None):
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

    async def send_participants(self, roster) -> None:
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


class FakeUser:
    def __init__(self, name: str, id: int) -> None:
        self.name = name
        self.id = id


class FakeDiscordClient:
    def __init__(self, name="MULCA", id=1, guilds=(900,)) -> None:
        self.user = FakeUser(name, id)
        self.latency = 0.042
        self._guilds = set(guilds)

    def get_channel(self, channel_id):
        return None

    def get_guild(self, guild_id):
        return object() if guild_id in self._guilds else None

    def is_ready(self) -> bool:
        return True


class FakeRegistry:
    def __init__(self) -> None:
        self.sessions: dict = {}
        self.restarted: list[str] = []
        self.closed: list[tuple[str, float | None]] = []
        self.runs = 0

    async def restart(self, conversation_id, wait=5.0) -> bool:
        self.restarted.append(conversation_id)
        return True

    async def close(self, conversation_id, *, wait=None) -> bool:
        self.closed.append((conversation_id, wait))
        self.sessions.pop(conversation_id, None)
        return True

    def find(self, conversation_id):
        return self.sessions.get(conversation_id)

    async def run(self, *args, **kwargs):
        self.runs += 1


class FakeBridge:
    def __init__(self) -> None:
        self.roster_updates = 0
        self.disconnected = False

    async def update_participants(self) -> None:
        self.roster_updates += 1

    async def disconnect(self) -> None:
        self.disconnected = True


def make_runtime(**client_kwargs) -> BotRuntime:
    runtime = BotRuntime(
        client=FakeDiscordClient(**client_kwargs),
        registry=FakeRegistry(),
        instances=[ALPHA],
    )
    runtime.active.append(ALPHA)
    return runtime


async def test_restarting_a_link_restarts_its_session_and_refreshes_voice():
    runtime = make_runtime()
    bridge = runtime.voice[ALPHA.name] = FakeBridge()

    outcome = await runtime.restart_link(ALPHA)

    assert outcome == RestartOutcome(instance=ALPHA, confirmed=True)
    assert runtime.registry.restarted == ["instance:team-alpha"]
    assert bridge.roster_updates == 1


async def test_a_paused_bot_leaves_voice_closes_sessions_and_ignores_messages():
    runtime = make_runtime()
    bridge = runtime.voice[ALPHA.name] = FakeBridge()
    runtime.registry.sessions = {"instance:team-alpha": object(), "dm:5": object()}

    await runtime.pause()

    class Message:
        class author:
            bot = False
            id = 5

        class channel:
            id = 111

        content = "hello?"

    await runtime.on_message(Message())

    assert bridge.disconnected
    assert runtime.voice == {}
    assert {closed for closed, _ in runtime.registry.closed} == {
        "instance:team-alpha",
        "dm:5",
    }
    assert runtime.registry.runs == 0


def test_status_reports_each_link():
    runtime = make_runtime()

    status = runtime.status()

    assert status.name == "MULCA"
    assert status.online and not status.paused
    assert status.latency_ms == pytest.approx(42)
    [link] = status.links
    assert link.name == "team-alpha"
    assert not link.session_open
    assert "can't see channel 111" in link.problems


def test_the_manager_finds_the_bot_serving_a_channel_and_resolves_targets():
    alpha = make_runtime(name="MULCA", id=1, guilds=(900,))
    beta = make_runtime(name="MULCA 2", id=2, guilds=(900, 901))
    beta.active[:] = [
        MulcaInstance(name="team-beta", text_channel_id=333, voice_channel_id=444)
    ]
    manager = BotManager([alpha, beta])

    assert manager.link_for_channel(444)[0] is beta
    assert manager.link_for_channel(999) is None
    assert manager.resolve("all", 900) == [alpha, beta]
    assert manager.resolve(None, 901) == [beta]
    assert manager.resolve("mulca 2", 900) == [beta]
    assert manager.resolve("2", 900) == [beta]
    # Never a bot outside the server the command came from.
    assert manager.resolve("MULCA", 901) == []


# ----------------------------------------------------------------------
# What the commands say
# ----------------------------------------------------------------------


def test_the_restart_reply_says_whether_the_memory_was_saved():
    saved = restart_message("@Ada", RestartOutcome(ALPHA, confirmed=True))
    unsure = restart_message("@Ada", RestartOutcome(ALPHA, confirmed=False))

    assert "remembers" in saved
    assert "didn't confirm" in unsure


async def test_control_stops_and_starts_only_the_named_bot():
    alpha = make_runtime(name="MULCA", id=1)
    beta = make_runtime(name="MULCA 2", id=2)
    manager = BotManager([alpha, beta])

    stopped = await control(manager, "stop", "MULCA 2", 900)
    assert beta.paused and not alpha.paused
    assert "MULCA 2" in stopped

    await control(manager, "start", "all", 900)
    assert not beta.paused

    assert "No MULCA bot" in await control(manager, "stop", "nobody", 900)


def test_status_text_lists_bots_links_and_problems():
    runtime = make_runtime()

    text = format_status([runtime.status()])

    assert "**MULCA**: online" in text
    assert "<#111>" in text and "<#222>" in text
    assert "can't see channel 111" in text
    assert format_status([]) == "No MULCA bot is in this server."


def test_the_primary_bot_registers_restart_and_the_admin_group():
    import discord

    from mulca_discord.commands import install_commands
    from mulca_discord.discord_client import build_discord_client

    client = build_discord_client(muca_server_url="ws://unused/", instances=[ALPHA])
    tree = install_commands(BotManager([client.mulca_runtime]))

    commands = {command.name: command for command in tree.get_commands()}
    assert set(commands) == {"restart", "mulca"}
    assert {sub.name for sub in commands["mulca"].commands} == {
        "status",
        "restart",
        "stop",
        "start",
    }
    # Hidden from everyone without Manage Server, and never in DMs.
    assert commands["mulca"].default_permissions == discord.Permissions(manage_guild=True)
    assert commands["mulca"].guild_only
    assert commands["restart"].guild_only
