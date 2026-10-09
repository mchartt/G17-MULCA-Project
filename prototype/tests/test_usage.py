"""
Spending limits (usage.py, /mulca limit|usage), the stages a bot goes
through on the way to one, and what MULCA tells its users about itself
(messages.py): each problem once when raised, and again only for an
@mention.
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


def usage_event(cost: float, agent: str = "main", **tokens) -> dict:
    return {"event": "usage", "agent": agent, "costUsd": cost, **tokens}


# ----------------------------------------------------------------------
# Spending
# ----------------------------------------------------------------------


def test_spending_is_recorded_per_bot_day_and_agent():
    usage = meter()
    t = at(2026, 10, 6, 10, 0)

    usage.record(1, usage_event(1.5, freshText=10, cachedAudio=5), t)
    usage.record(1, usage_event(0.5, freshText=1, outAudio=2), t)
    usage.record(1, usage_event(0.25, "transcription", freshAudio=100), t)
    usage.record(2, usage_event(4.0), t)
    usage.record(None, usage_event(9.0), t)  # not logged in yet

    day = "2026-10-06"
    assert usage._store.cost(1, day, day) == 2.25
    assert usage._store.cost(None, day, day) == 6.25
    assert usage.details(1, t)["daily"] == {
        "main": (11, 0, 0, 5, 0, 2, 2.0),
        "transcription": (0, 0, 100, 0, 0, 0, 0.25),
    }


def test_days_start_at_midnight_in_rome_weeks_on_monday_months_on_the_1st():
    usage = meter()
    usage.record(1, usage_event(1.0), at(2026, 10, 24, 12, 0))
    usage.record(1, usage_event(2.0), at(2026, 10, 25, 23, 59))
    usage.record(1, usage_event(4.0), at(2026, 11, 1, 0, 1))

    def spent(*when) -> dict:
        return {
            b.kind: b.used for b in usage.budgets(1, at(*when)) if b.scope == "bot"
        }

    assert spent(2026, 10, 25, 23, 59) == {"daily": 2.0, "weekly": 3.0, "monthly": 3.0}
    # Sunday 1 November: a new month, and Monday the 26th began a new week.
    assert spent(2026, 11, 1, 0, 1) == {"daily": 4.0, "weekly": 4.0, "monthly": 4.0}

    daily, weekly, monthly = usage.budgets(1, at(2026, 10, 25, 23, 59))[:3]
    assert daily.resets_at == datetime(2026, 10, 26, tzinfo=ROME)
    assert weekly.resets_at == datetime(2026, 10, 26, tzinfo=ROME)
    assert monthly.resets_at == datetime(2026, 11, 1, tzinfo=ROME)


def test_every_bot_gets_the_defaults_unless_overridden_and_the_pool_ten_times_them():
    usage = meter()
    store = usage._store

    assert usage.limits(1) == {"bot": (30.0, 50.0, 100.0), "pool": (300.0, 500.0, 1000.0)}

    store.set_limit("each", 10.0, 20.0, None)
    assert usage.limits(1) == {"bot": (10.0, 20.0, None), "pool": (100.0, 200.0, None)}

    store.set_limit("bot:1", 1.0, None, None)
    store.set_limit("pool", 5.0, None, None)
    assert usage.limits(1) == {"bot": (1.0, None, None), "pool": (5.0, None, None)}
    assert usage.limits(2) == {"bot": (10.0, 20.0, None), "pool": (5.0, None, None)}


def test_the_stage_follows_the_most_used_limit():
    usage = meter()
    usage._store.set_limit("bot:1", 10.0, None, None)
    t = at(2026, 10, 6, 10, 0)

    for cost, level in [(4.9, 0), (0.1, 1), (2.0, 2), (2.0, 3), (1.0, 4)]:
        usage.record(1, usage_event(cost), t)
        assert usage.stage(1, t)[0] == level

    _, budget = usage.stage(1, t)
    assert (budget.kind, budget.scope, budget.share) == ("daily", "bot", 1.0)
    # The next day it starts over.
    assert usage.stage(1, at(2026, 10, 7, 10, 0))[0] == 0


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
    # These tests are about usage/offline/attachment notices, not the daily
    # greeting -- pre-mark it as already sent today so it doesn't show up
    # in channel.sent alongside what each test actually checks.
    today = datetime.now(runtime.usage.tz).date().isoformat()
    runtime.store.set_greeting_state(
        ALPHA.conversation_id, last_greeted_date=today, had_a_session=True
    )
    return runtime, channel


def tagged(runtime, channel, **fields):
    msg = message(5, channel, f"<@{runtime.user_id}> hi")
    msg.mentions = [runtime.client.user]
    for name, value in fields.items():
        setattr(msg, name, value)
    return msg


class UsageSession:
    """What _on_usage needs of a session: where its replies go."""

    def __init__(self, channel) -> None:
        class Replies:
            pass

        self.replies = Replies()
        self.replies.channel = channel


async def test_spending_goes_through_each_stage_once_and_back_when_raised():
    runtime, channel = runtime_with_channel()
    runtime.store.set_limit("bot:1", 10.0, None, None)
    session = UsageSession(channel)

    async def spend(cost: float) -> None:
        await runtime._on_usage(session, usage_event(cost))
        await asyncio.sleep(0)  # voice changes run in the background

    await spend(5.0)
    await spend(0.1)  # the same stage: nothing new to say
    budget = runtime.usage.stage(1)[1]
    assert channel.sent == [messages.limit_warning(budget)]

    await spend(2.0)
    assert channel.sent[1:] == [messages.listening_only(budget)]
    assert runtime.registry.text_replies
    assert await runtime.voice_active(ALPHA)

    await spend(2.0)
    assert channel.sent[2:] == [messages.text_only(budget)]
    assert not await runtime.voice_active(ALPHA)

    # Typed messages still get through, until the limit itself.
    await runtime.on_message(message(5, channel))
    assert len(runtime.registry.scopes) == 1

    await spend(1.0)
    assert channel.sent[3:] == [messages.limit_reached(budget)]
    await runtime.on_message(message(5, channel))
    assert len(runtime.registry.scopes) == 1
    await runtime.on_message(tagged(runtime, channel))
    assert channel.sent[4:] == [messages.limit_reached(budget)]

    # Never a word about money in the channel.
    assert not any("$" in text for text in channel.sent)

    runtime.store.set_limit("bot:1", 100.0, None, None)
    await runtime.recheck_limits()
    await asyncio.sleep(0)
    assert channel.sent[5:] == [messages.stage_lifted(0)]
    assert not runtime.registry.text_replies
    assert await runtime.voice_active(ALPHA)

    await runtime.on_message(message(5, channel))
    assert len(runtime.registry.scopes) == 2


async def test_a_raised_limit_can_lift_part_of_the_way():
    runtime, channel = runtime_with_channel()
    runtime.store.set_limit("bot:1", 10.0, None, None)
    await runtime._on_usage(UsageSession(channel), usage_event(10.0))
    await asyncio.sleep(0)

    runtime.store.set_limit("bot:1", 12.0, None, None)  # now at 83%
    await runtime.recheck_limits()
    await asyncio.sleep(0)

    assert channel.sent[-1] == messages.stage_lifted(2)
    assert runtime.registry.text_replies
    assert await runtime.voice_active(ALPHA)


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

    reply = await set_limit(manager, "all", 4, 10, None, GUILD)
    assert "$4.00 a day, $10.00 a week, $100.00 a month" in reply and "10x" in reply
    assert runtime.store.limit("each") == (4.0, 10.0, 100.0)

    # What isn't given stays as it was.
    reply = await set_limit(manager, "MULCA", 1.5, None, None, GUILD)
    assert reply.startswith("**MULCA**: $1.50 a day, $10.00 a week, $100.00 a month")
    assert runtime.store.limit("bot:1") == (1.5, 10.0, 100.0)

    assert "Give a daily, weekly or monthly limit" in await set_limit(
        manager, "pool", None, None, None, GUILD
    )
    assert "No MULCA bot called" in await set_limit(manager, "nobody", 1, None, None, GUILD)

    runtime.usage.record(1, usage_event(0.6, freshText=1000, cachedText=200))
    usage = format_usage(manager, None, GUILD)
    assert (
        "**MULCA**: today $0.60 of $1.50 (40%) · this week $0.60 of $10.00 (6%) · "
        "this month $0.60 of $100.00 (1%) -- now: normal"
    ) in usage
    assert "All bots together: today $0.60 of $40.00" in usage
    assert "main:" not in usage

    details = format_usage(manager, "MULCA", GUILD, details=True)
    assert "main: text in 1,000 (+200 cached) · audio in 0 (+0 cached)" in details

    await clear_limit(manager, "MULCA", GUILD)
    assert runtime.store.limit("bot:1") is None
