"""
Usage limits (usage.py, /mulca limit|usage) and what MULCA tells its users
about itself (messages.py): each problem once when raised, and again only
for an @mention.
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from mulca_discord import messages
from mulca_discord.commands import clear_limit, format_usage, set_limit
from mulca_discord.links import LinkStore
from mulca_discord.messages import Notices
from mulca_discord.runtime import BotManager
from mulca_discord.usage import UsageMeter

from tests.test_control import ALPHA, GUILD, FakeChannel, FakeMember, make_runtime, message

ROME = ZoneInfo("Europe/Rome")


def at(*args) -> float:
    return datetime(*args, tzinfo=ROME).timestamp()


def meter() -> UsageMeter:
    return UsageMeter(LinkStore(":memory:"), tz=ROME)


# ----------------------------------------------------------------------
# Counting
# ----------------------------------------------------------------------


def test_a_channel_counts_one_minute_per_minute_and_channels_add_up():
    usage = meter()
    t = at(2026, 10, 6, 10, 0, 5)

    assert usage.mark_active(1, "channel:1", t)
    assert not usage.mark_active(1, "channel:1", t + 30)  # same minute
    assert usage.mark_active(1, "channel:2", t + 30)  # another channel
    assert usage.mark_active(1, "channel:1", t + 60)
    assert not usage.mark_active(None, "channel:3", t)  # not logged in yet

    assert usage.used(1, t + 60) == (3, 3)
    assert usage.used(2, t + 60) == (0, 0)
    assert usage.used(None, t + 60) == (3, 3)


def test_days_start_at_midnight_in_rome_and_weeks_on_monday():
    usage = meter()
    sunday_night = at(2026, 10, 25, 23, 59, 30)  # the night clocks go back
    monday = at(2026, 10, 26, 0, 0, 30)

    usage.mark_active(1, "channel:1", at(2026, 10, 24, 12, 0))
    usage.mark_active(1, "channel:1", sunday_night)
    usage.mark_active(1, "channel:1", monday)

    assert usage.used(1, sunday_night) == (1, 2)
    assert usage.used(1, monday) == (1, 1)

    usage._store.set_limit("each", 60, 600)
    daily, weekly = usage.budgets(1, sunday_night)[:2]
    assert daily.resets_at == datetime(2026, 10, 26, tzinfo=ROME)
    assert weekly.resets_at == datetime(2026, 10, 26, tzinfo=ROME)


def test_a_bots_own_limit_replaces_the_default_and_the_pool_is_ten_times_it():
    usage = meter()
    store = usage._store

    assert usage.limits(1) == {}

    store.set_limit("each", 240, 600)
    assert usage.limits(1) == {"bot": (240, 600), "pool": (2400, 6000)}

    store.set_limit("bot:1", 60, None)
    store.set_limit("pool", 100, None)
    assert usage.limits(1) == {"bot": (60, None), "pool": (100, None)}
    assert usage.limits(2) == {"bot": (240, 600), "pool": (100, None)}


def test_the_limit_reported_is_the_one_with_the_longest_wait():
    usage = meter()
    usage._store.set_limit("each", 1, 2)
    monday = at(2026, 10, 5, 10, 0)
    tuesday = at(2026, 10, 6, 10, 0)

    usage.mark_active(1, "channel:1", monday)
    assert usage.check(1, monday).kind == "daily"
    assert usage.check(1, tuesday) is None
    assert usage.tightest(1, tuesday).left == 1

    usage.mark_active(1, "channel:1", tuesday)
    over = usage.check(1, tuesday)
    assert (over.kind, over.scope) == ("weekly", "bot")


# ----------------------------------------------------------------------
# Notices
# ----------------------------------------------------------------------


class SentChannel(FakeChannel):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.sent: list[str] = []

    async def send(self, content) -> None:
        self.sent.append(content)


async def test_a_notice_is_posted_once_and_its_resolution_where_it_was_raised():
    notices = Notices()
    first, second = SentChannel(1, None), SentChannel(2, None)

    assert await notices.raise_("offline", first, "down")
    assert not await notices.raise_("offline", second, "down")
    await notices.remind(second)
    await notices.resolve("offline", "up")
    await notices.resolve("offline", "up")

    assert first.sent == ["down", "up"]
    assert second.sent == ["down"]


# ----------------------------------------------------------------------
# What a bot does and says
# ----------------------------------------------------------------------


def runtime_with_channel():
    runtime = make_runtime()
    channel = SentChannel(111, runtime.client.guilds[GUILD], [FakeMember(5, "Ada")])
    runtime.client.channels[111] = channel
    return runtime, channel


def tagged(runtime, channel, **fields):
    msg = message(5, channel, f"<@{runtime.user_id}> hi")
    msg.mentions = [runtime.client.user]
    for name, value in fields.items():
        setattr(msg, name, value)
    return msg


async def test_over_its_limit_it_says_so_once_then_only_when_tagged():
    runtime, channel = runtime_with_channel()
    runtime.store.set_limit("bot:1", 1, None)

    # The first minute is allowed, with the heads-up that it's the last one.
    await runtime.on_message(message(5, channel))
    assert len(runtime.registry.scopes) == 1
    assert channel.sent == [messages.limit_warning(runtime.usage.tightest(1))]

    await runtime.on_message(message(5, channel))
    await runtime.on_message(message(5, channel))
    await asyncio.sleep(0)  # the stop runs in the background

    reached = messages.limit_reached(runtime.usage.check(1))
    assert channel.sent[1:] == [reached]
    assert len(runtime.registry.scopes) == 1  # nothing more reached the server

    await runtime.on_message(tagged(runtime, channel))
    assert channel.sent[2:] == [reached]

    # A restart never resets usage.
    await runtime.restart_link(ALPHA)
    await runtime.on_message(message(5, channel))
    assert channel.sent[3:] == []
    assert len(runtime.registry.scopes) == 1

    runtime.store.clear_limit("bot:1")
    await runtime.recheck_limits()
    assert channel.sent[3:] == [messages.AVAILABLE_AGAIN]

    await runtime.on_message(message(5, channel))
    assert len(runtime.registry.scopes) == 2


async def test_offline_it_says_so_once_and_once_more_when_back():
    runtime, channel = runtime_with_channel()
    working = runtime.registry.run

    async def unreachable(*args, **kwargs):
        raise ConnectionError("down")

    runtime.registry.run = unreachable
    await runtime.on_message(message(5, channel))
    await runtime.on_message(message(5, channel))
    await runtime.on_message(tagged(runtime, channel))
    assert channel.sent == [messages.OFFLINE, messages.OFFLINE]

    runtime.registry.run = working
    await runtime.on_message(message(5, channel))
    await runtime.on_message(message(5, channel))
    assert channel.sent[2:] == [messages.BACK_ONLINE]


async def test_paused_it_says_so_once_then_only_when_tagged():
    runtime, channel = runtime_with_channel()
    await runtime.pause()

    await runtime.on_message(message(5, channel))
    await runtime.on_message(message(5, channel))
    await runtime.on_message(tagged(runtime, channel))

    assert channel.sent == [messages.PAUSED, messages.PAUSED]
    assert runtime.registry.scopes == []


async def test_attachments_are_mentioned_only_when_it_is_tagged():
    runtime, channel = runtime_with_channel()

    untagged = message(5, channel)
    untagged.attachments = [object()]
    await runtime.on_message(untagged)
    assert channel.sent == []

    await runtime.on_message(tagged(runtime, channel, attachments=[object()]))
    assert channel.sent == [messages.ATTACHMENTS]


async def test_a_server_error_is_told_once_until_a_reply_comes_through():
    runtime, channel = runtime_with_channel()

    class Session:
        class scope:
            conversation_id = "channel:111"

        class replies:
            pass

    Session.replies.channel = channel

    await runtime._on_server_error(Session, "boom")
    await runtime._on_server_error(Session, "boom")
    runtime._on_reply(Session, False)
    await runtime._on_server_error(Session, "boom")
    runtime._on_reply(Session, True)
    await runtime._on_server_error(Session, "boom")

    assert channel.sent == [messages.TURN_FAILED, messages.TURN_FAILED]


# ----------------------------------------------------------------------
# /mulca limit, /mulca usage
# ----------------------------------------------------------------------


async def test_limits_are_set_shown_and_cleared():
    runtime, _ = runtime_with_channel()
    manager = BotManager([runtime], store=runtime.store)

    reply = await set_limit(manager, "all", 4, 10, GUILD)
    assert "4h 0m a day, 10h 0m a week" in reply and "10x" in reply
    assert runtime.store.limit("each") == (240, 600)

    reply = await set_limit(manager, "MULCA", 1.5, None, GUILD)
    assert reply.startswith("**MULCA**: 1h 30m a day, no limit a week")
    assert runtime.store.limit("bot:1") == (90, None)

    assert "Give a daily or a weekly limit" in await set_limit(manager, "pool", None, None, GUILD)
    assert "No MULCA bot called" in await set_limit(manager, "nobody", 1, None, GUILD)

    usage = format_usage(manager, None, GUILD)
    assert "**MULCA**: today 0m of 1h 30m, this week 0m of no limit" in usage
    assert "All bots together: today 0m of 40h 0m, this week 0m of 100h 0m" in usage

    await clear_limit(manager, "MULCA", GUILD)
    assert runtime.store.limit("bot:1") is None
