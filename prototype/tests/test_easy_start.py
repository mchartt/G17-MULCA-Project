"""
Starting with Cadence in one step: paste the web space's invite link in the
channel (Slack or Discord) and it is linked; Cadence greets a Slack channel
it is added to. Fake Slack and Discord, a real local MUCA-Server.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from mulca_discord.invites import invite_in
from mulca_discord.sessions import SessionRegistry
from mulca_discord.slack import SlackHub
from mulca_discord.slack.hub import WELCOME
from tests.test_coordinator_discord import coordinator_server  # noqa: F401  (pytest fixture)
from tests.test_cross_channel import discord_side
from tests.test_slack import BOT, CHIARA, FakeSlack
from tests.test_web import Tab, web  # noqa: F401  (pytest fixture)


def test_only_an_invite_link_counts():
    assert invite_in("join us: https://cadence-coordinator.onrender.com/join/ab12cd34 thanks") == "AB12CD34"
    assert invite_in("<https://cadence.app/login?code=AB12CD34>") == "AB12CD34"  # Slack wraps links
    assert invite_in("https://x.org/?lang=it&code=Q1W2E3") == "Q1W2E3"
    assert invite_in("the code is AB12CD34") is None  # a bare word never links
    assert invite_in("see https://example.com/join") is None
    assert invite_in("") is None


async def space(http, ws_url):
    async with httpx.AsyncClient(base_url=http) as api:
        made = (await api.post("/api/groups", json={"groupName": "Group 17", "displayName": "Bruno"})).json()
    tab = await Tab.open(ws_url, made["token"])
    await tab.send(type="command", command="state", requestId="s0")
    await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "s0")
    return made, tab


async def test_slack_welcome_then_a_pasted_link_links_the_channel(web, coordinator_server):  # noqa: F811
    _, http, ws_url = web
    made, tab = await space(http, ws_url)
    slack = FakeSlack()
    hub = SlackHub(slack, coordinator_server)
    try:
        await hub.on_joined({"type": "member_joined_channel", "user": CHIARA, "channel": "C1"})
        assert slack.posts == []  # someone else joining: nothing
        await hub.on_joined({"type": "member_joined_channel", "user": BOT, "channel": "C1"})
        assert slack.posts[-1]["text"] == WELCOME

        link = f"here it is <https://cadence-coordinator.onrender.com/join/{made['inviteCode']}>"
        await hub.on_message({"type": "message", "channel": "C1", "user": CHIARA, "text": link})
        said = slack.posts[-1]["text"]
        assert "Linked to the web space" in said and "/coordinator plan" in said
        # The link is a command, not a chat line: the web chat did not get it.
        assert not [e for e in tab.seen if e["type"] == "message" and e["message"].get("channel") == "slack"]
        assert "No charter yet" in await hub.on_command("C1", CHIARA, "plan")
    finally:
        await tab.ws.close()
        await hub.close()


async def test_discord_a_pasted_link_links_the_channel(web, coordinator_server):  # noqa: F811
    _, http, ws_url = web
    made, tab = await space(http, ws_url)
    bridge, bot, _, channel = discord_side(coordinator_server)
    try:
        message = SimpleNamespace(
            content=f"https://cadence-coordinator.onrender.com/join/{made['inviteCode']}",
            guild=SimpleNamespace(id=1),
            channel=SimpleNamespace(id=42, send=channel.send),
            author=SimpleNamespace(id=9001),
        )
        assert await bridge.invite(message)
        assert "Linked to the web space" in channel.lines[-1] and "/coordinator voice" in channel.lines[-1]
        assert not await bridge.invite(SimpleNamespace(content="hello", guild=SimpleNamespace(id=1)))
    finally:
        await tab.ws.close()
        await bot.registry.close_all()
        SessionRegistry.on_coordinator_event = None
