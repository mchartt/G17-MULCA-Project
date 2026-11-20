"""
Matteo, 20/11: Discord and Slack answer messages for Cadence like the web app
(addressing.for_cadence, command "ask"), show that Cadence is working, and
never lose a late answer. The server's model is faked here: these tests prove
the routing and delivery, not what a real model answers.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

from mulca_discord.coordinator.bridge import ASK_SLOW, CoordinatorBridge


class Channel:
    def __init__(self) -> None:
        self.id = 42
        self.sent: list[str] = []
        self.typing_used = 0

    async def send(self, text, **_):
        self.sent.append(text)

    @asynccontextmanager
    async def typing(self):
        self.typing_used += 1
        yield


def make_bridge(answers):
    link = SimpleNamespace(text_channel_id=42)
    bot = SimpleNamespace(roster_text=lambda link: {1: "Ada", 2: "Bruno"})
    bridge = CoordinatorBridge(SimpleNamespace(bots=[bot], link_for_channel=lambda cid: (bot, link) if cid == 42 else None))
    asked = []

    async def send_to(channel_id, request_id, message, **_):
        asked.append((message.args, request_id, message.member_id))
        return answers.pop(0)

    bridge._send_to = send_to
    return bridge, asked


async def test_a_call_to_cadence_is_answered_in_the_channel_while_typing_shows():
    bridge, asked = make_bridge([{"event": "coordinator_notice", "ok": True, "text": "Hai una task: **Frontend Application**."}])
    channel = Channel()
    assert await bridge.chat(channel, 1, "Oii Cadence, controlla le mie task.") is True
    assert asked[0][0]["question"] == "controlla le mie task." and asked[0][2] == 1  # the author's id: who asks
    assert channel.sent == ["Hai una task: **Frontend Application**."] and channel.typing_used == 1


async def test_talk_about_cadence_is_offered_as_maybe_and_silence_posts_nothing():
    bridge, asked = make_bridge([{"event": "coordinator_notice", "ok": True, "text": ""}])
    channel = Channel()
    assert await bridge.chat(channel, 1, "Secondo me Cadence è inutile") is True
    assert asked[0][0]["question"] == "Secondo me Cadence è inutile" and asked[0][0]["maybe"] is True
    assert channel.sent == [] and channel.typing_used == 0


async def test_a_message_not_for_cadence_goes_on_as_before():
    bridge, asked = make_bridge([])
    assert await bridge.chat(Channel(), 1, "ci vediamo domani alle 10") is False and asked == []
    other = Channel()
    other.id = 7  # not a linked channel
    assert await bridge.chat(other, 1, "Cadence, ciao") is False


async def test_an_at_mention_of_the_bot_is_a_call():
    bridge, asked = make_bridge([{"event": "coordinator_notice", "ok": True, "text": "Eccomi."}])
    channel = Channel()
    assert await bridge.chat(channel, 1, "@MULCA mi senti?", tagged=True) is True
    assert "maybe" not in asked[0][0] and channel.sent == ["Eccomi."]


async def test_a_late_answer_is_posted_when_it_comes():
    bridge, asked = make_bridge([None])
    channel = Channel()
    await bridge.chat(channel, 1, "Cadence, sono al 30%.")
    assert channel.sent == [ASK_SLOW]
    request_id = asked[0][1]
    await bridge.on_event(SimpleNamespace(), {"event": "coordinator_notice", "ok": True, "text": "Card pronta.", "requestId": request_id})
    await bridge.on_event(SimpleNamespace(), {"event": "coordinator_notice", "ok": True, "text": "Card pronta.", "requestId": request_id})
    assert channel.sent == [ASK_SLOW, "Card pronta."]


async def test_a_follow_up_right_after_an_answer_is_offered_as_maybe():
    bridge, asked = make_bridge([
        {"event": "coordinator_notice", "ok": True, "text": "Frontend Application è al 0%."},
        {"event": "coordinator_notice", "ok": True, "text": "Card pronta: confermala."},
    ])
    channel = Channel()
    await bridge.chat(channel, 1, "Cadence, com'è la mia task?")
    # A follow-up is asked in the background AND sent on as user_text (False):
    # the proactive judge still reads it; R10 on the server stops a second reply.
    assert await bridge.chat(channel, 1, "sono al 30%") is False
    await bridge.wait_for_answers()
    assert asked[1][0]["question"] == "sono al 30%" and asked[1][0]["maybe"] is True


class Slack:
    bot_user = "U0BOT"

    def __init__(self) -> None:
        self.posts: list[str] = []

    async def post(self, channel, text, blocks=None):
        self.posts.append(text)
        return str(len(self.posts))

    async def update(self, channel, ts, text, blocks=None):
        self.posts[int(ts) - 1] = text

    async def roster(self, channel):
        return {"U1": "Ada", "U2": "Bruno"}


def make_slack(answers):
    from mulca_discord.slack import SlackHub

    api = Slack()
    hub = SlackHub(api, "ws://unused")
    asked = []

    async def fake_ask(channel, user, build):
        message = build("req-%d" % len(asked))
        asked.append(message)
        return answers.pop(0)

    hub._ask = fake_ask
    return hub, api, asked


async def test_slack_shows_thinking_then_the_answer_in_its_place():
    from mulca_discord.slack.hub import THINKING

    hub, api, asked = make_slack([None])
    await hub.on_message({"type": "message", "channel": "C1", "user": "U1", "text": "Oii Cadence, sono al 30%."})
    assert api.posts == [THINKING] and asked[0].args["question"] == "sono al 30%."
    await hub._on_coordinator_event(
        SimpleNamespace(scope=SimpleNamespace(conversation_id="slack:C1")),
        {"event": "coordinator_notice", "ok": True, "text": "Card pronta: **30%**.", "requestId": "req-0"},
    )
    assert api.posts == ["Card pronta: *30%*."]  # Slack's bold


async def test_slack_talk_about_cadence_stays_silent():
    hub, api, asked = make_slack([{"event": "coordinator_notice", "ok": True, "text": ""}])
    await hub.on_message({"type": "message", "channel": "C1", "user": "U1", "text": "Mannaggia mi sa che cadence non basta"})
    assert asked[0].args["maybe"] is True and api.posts == []


async def test_discord_says_unavailable_when_the_server_fails_not_that_an_answer_will_come():
    bridge, _ = make_bridge([{"event": "coordinator_notice", "ok": False, "text": "The coordinator is not available right now."}])
    channel = Channel()
    await bridge.chat(channel, 1, "Cadence, mi senti?")
    assert channel.sent == ["The coordinator is not available right now."] and bridge._late == {}


async def test_discord_gives_up_on_a_late_answer_that_never_comes():
    from mulca_discord.coordinator.bridge import UNAVAILABLE

    bridge, asked = make_bridge([None])
    channel = Channel()
    await bridge.chat(channel, 1, "Cadence, sono al 30%.")
    await bridge.give_up(asked[0][1])
    assert channel.sent == [ASK_SLOW, UNAVAILABLE]


async def test_slack_thinking_line_becomes_unavailable_if_no_answer_comes():
    from mulca_discord.slack.hub import UNAVAILABLE

    hub, api, asked = make_slack([None])
    await hub.on_message({"type": "message", "channel": "C1", "user": "U1", "text": "Cadence, sono al 30%."})
    await hub.give_up("req-0")
    assert api.posts == [UNAVAILABLE]
