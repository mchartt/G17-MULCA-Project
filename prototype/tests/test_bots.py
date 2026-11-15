"""
Several bots in one process: adding one by token (/mulca bot add), running
each in its own supervised task so one failing never stops the others,
removing it again, and never showing or logging a token.
"""

import asyncio
import logging

import discord
import pytest

import mulca_discord.runtime as runtime_module
from mulca_discord.commands import TokenProbe, add_bot, list_bots, remove_bot
from mulca_discord.links import BotRecord, Link, LinkStore
from mulca_discord.runtime import BotManager, BotRuntime

TOKEN = "M" * 72
PRIMARY_TOKEN = "P" * 72


class FakeUser:
    def __init__(self, id: int, name: str) -> None:
        self.id = id
        self.name = name


class FakeRegistry:
    sessions: dict = {}

    async def close(self, conversation_id, *, wait=None) -> bool:
        return True

    async def close_all(self) -> None:
        pass


class FakeGatewayClient:
    """Stands in for discord.Client.start: logs in, or fails as told."""

    behaviours: list = []
    started: list[str] = []

    def __init__(self, store: LinkStore) -> None:
        self.user = None
        self.latency = 0.0
        self.mulca_runtime = BotRuntime(client=self, registry=FakeRegistry(), store=store, is_primary=False)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        pass

    async def start(self, token: str) -> None:
        FakeGatewayClient.started.append(token)
        behaviour = FakeGatewayClient.behaviours.pop(0) if FakeGatewayClient.behaviours else "online"
        if isinstance(behaviour, BaseException):
            raise behaviour

        self.user = FakeUser(2, "MULCA 2")
        for hook in self.mulca_runtime.after_ready:
            await hook(self.mulca_runtime)
        await asyncio.Event().wait()

    def get_guild(self, guild_id):
        return None

    def get_channel(self, channel_id):
        return None


def primary_runtime(store: LinkStore) -> BotRuntime:
    class PrimaryClient:
        user = FakeUser(1, "MULCA")
        latency = 0.0

        def get_guild(self, guild_id):
            return None

    return BotRuntime(client=PrimaryClient(), registry=FakeRegistry(), store=store)


@pytest.fixture
def manager():
    FakeGatewayClient.behaviours = []
    FakeGatewayClient.started = []
    store = LinkStore(":memory:")
    store.register_bot(1, "MULCA", is_primary=True)
    built = BotManager(
        [primary_runtime(store)],
        store=store,
        client_factory=lambda: FakeGatewayClient(store),
        primary_token=PRIMARY_TOKEN,
    )
    yield built


def probe_for(bot_id=2, name="MULCA 2", missing=(), public=True):
    async def probe(token):
        return TokenProbe(
            bot_id=bot_id,
            name=name,
            application_id=bot_id,
            missing_intents=tuple(missing),
            public=public,
        )

    return probe


async def rejected(token):
    raise discord.LoginFailure("bad token")


async def test_adding_a_bot_saves_its_token_starts_it_and_gives_an_invite(manager):
    reply = await add_bot(manager, TOKEN, added_by=5, probe=probe_for())

    assert "Added **MULCA 2** (online)" in reply
    assert "client_id=2" in reply and "permissions=36768768" in reply
    assert manager.store.added_bots() == [BotRecord(2, "MULCA 2", TOKEN)]
    assert manager.bot_by_id(2) is not None
    assert TOKEN not in reply

    await manager.stop_added_bots()


@pytest.mark.parametrize(
    ("token", "probe", "expected"),
    [
        (PRIMARY_TOKEN, probe_for(), "main MULCA bot's token"),
        (TOKEN, rejected, "Discord rejected that token"),
        (TOKEN, probe_for(missing=["Message Content Intent"]), "Message Content Intent"),
        (TOKEN, probe_for(bot_id=1, name="MULCA"), "already part of MULCA"),
    ],
    ids=["the primary's token", "a bad token", "intents off", "a running bot"],
)
async def test_tokens_that_cant_be_added_are_refused(manager, token, probe, expected):
    reply = await add_bot(manager, token, probe=probe)

    assert expected in reply
    assert manager.store.added_bots() == []


async def test_added_bots_start_with_the_process(manager):
    manager.store.add_bot(BotRecord(2, "MULCA 2", TOKEN))

    await manager.start_added_bots()
    for _ in range(50):
        if manager.states.get(2) == "online":
            break
        await asyncio.sleep(0.01)

    assert manager.states[2] == "online"
    assert FakeGatewayClient.started == [TOKEN]
    await manager.stop_added_bots()
    assert manager.bot_by_id(2) is None


async def test_a_rejected_token_fails_that_bot_only(manager):
    FakeGatewayClient.behaviours = [discord.LoginFailure("bad")]

    state = await manager.start_bot(BotRecord(2, "MULCA 2", TOKEN))

    assert state.startswith("failed: Discord rejected its token")
    assert [bot.user_id for bot in manager.bots] == [1]


async def test_a_crashed_bot_is_restarted(manager, monkeypatch):
    monkeypatch.setattr(runtime_module, "BOT_RETRY_DELAYS_SECONDS", (0.01, 0.01))
    FakeGatewayClient.behaviours = [RuntimeError("gateway hiccup"), "online"]

    await manager.start_bot(BotRecord(2, "MULCA 2", TOKEN), wait=False)
    for _ in range(100):
        if manager.states.get(2) == "online":
            break
        await asyncio.sleep(0.01)

    assert manager.states[2] == "online"
    assert FakeGatewayClient.started == [TOKEN, TOKEN]
    await manager.stop_added_bots()


async def test_a_bot_with_links_is_only_removed_with_force(manager):
    await add_bot(manager, TOKEN, probe=probe_for())
    manager.store.save(Link(text_channel_id=333, guild_id=900, bot_id=2))

    refused = await remove_bot(manager, "MULCA 2")
    assert "still serves <#333>" in refused
    assert manager.bot_by_id(2) is not None

    removed = await remove_bot(manager, "MULCA 2", force=True)
    assert "Removed **MULCA 2**" in removed
    assert manager.store.added_bots() == []
    assert manager.store.all_links() == []
    assert manager.bot_by_id(2) is None


async def test_the_main_bot_cant_be_removed(manager):
    assert "can't be removed" in await remove_bot(manager, "MULCA")


async def test_the_list_shows_every_bot_but_never_a_token(manager, caplog):
    caplog.set_level(logging.DEBUG)
    await add_bot(manager, TOKEN, probe=probe_for())

    listed = list_bots(manager)

    assert "**MULCA** (main, id 1)" in listed
    assert "**MULCA 2** (id 2): online" in listed
    assert TOKEN not in listed
    assert TOKEN not in caplog.text
    assert TOKEN not in repr(manager.store.added_bots())

    await manager.stop_added_bots()
