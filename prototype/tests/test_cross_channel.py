"""
Cross-channel, end to end: one real MUCA-Server (coordinator on, fake model),
the web adapter with a browser tab, and the Discord bridge with a fake channel.

A Discord channel is linked to a web space with the space's invite code. Then:
the project is one, a card made on the web is confirmed on Discord, and what is
written in one channel is shown in the other.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx

from mulca_discord.coordinator.bridge import CoordinatorBridge, scope_for
from mulca_discord.coordinator.texts import catchup_text, mirror_text, owner_text
from mulca_discord.sessions import SessionRegistry
from tests.test_coordinator_discord import coordinator_server  # noqa: F401  (pytest fixture)
from tests.test_web import Tab, web  # noqa: F401  (pytest fixture)

DISCORD_ROSTER = {9001: "Chiara", 9002: "Dario"}


class DiscordChannel:
    """A Discord text channel that records what the bot posts in it."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.cards: list[str] = []

    async def send(self, content=None, *, embed=None, view=None, allowed_mentions=None):
        channel = self
        if embed is None:
            self.lines.append(content)
            return None

        class Card:
            async def edit(self, *, embed, view):
                channel.cards.append(embed.footer.text)

        self.cards.append(embed.footer.text)
        return Card()


def discord_side(server_url):
    """The Discord bot as the bridge sees it: one linked channel, two members."""
    channel = DiscordChannel()
    link = SimpleNamespace(conversation_id="channel:42", listening_mode="", guild_id=1, text_channel_id=42)
    bot = SimpleNamespace(
        name="MULCA",
        registry=SessionRegistry(server_url),
        roster_text=lambda link: DISCORD_ROSTER,
        _channel_name_for=lambda link: "group-17",
        course_for=lambda guild_id: "aui",
        client=SimpleNamespace(get_channel=lambda channel_id: channel, add_dynamic_items=lambda *items: None),
    )
    bridge = CoordinatorBridge(SimpleNamespace(bots=[bot], link_for_channel=lambda channel_id: (bot, link)))
    bridge.attach()
    return bridge, bot, link, channel


def member(user_id):
    """A Discord interaction of this member in the linked channel."""
    said = []

    async def record(*args, **kwargs):
        said.append(args[0] if args else "deferred")

    return SimpleNamespace(
        channel_id=42,
        user=SimpleNamespace(id=user_id),
        response=SimpleNamespace(defer=record),
        followup=SimpleNamespace(send=record),
        said=said,
    )


async def until(check, timeout: float = 10.0) -> None:
    """Wait for something that arrives over the network a moment later."""
    async with asyncio.timeout(timeout):
        while not check():
            await asyncio.sleep(0.02)


async def say_on_discord(bot, link, channel, speaker, text):
    """What runtime.py does when a member writes in the linked channel."""

    async def action(client) -> None:
        await client.send_participants(DISCORD_ROSTER, modality="text")
        await client.send_user_text(speaker=speaker, speaker_name=DISCORD_ROSTER[speaker], text=text, mentions_assistant=False)

    await bot.registry.run(scope_for(bot, link), action, reply_channel=channel)


async def test_one_project_across_the_web_and_discord(web, coordinator_server):  # noqa: F811
    hub, http, ws_url = web
    async with httpx.AsyncClient(base_url=http) as api:
        ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
    tab = await Tab.open(ws_url, ada["token"])
    # The web space has a project file on the server once it was used.
    await tab.send(type="command", command="state", requestId="s0")
    await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "s0")

    bridge, bot, link, channel = discord_side(coordinator_server)
    try:
        # A wrong code is explained; the right one links the channel.
        wrong = await bridge.send_command(member(9001), "link", {"code": "ZZZZZZ"})
        assert not wrong["ok"] and "No web space" in wrong["text"]
        linked = await bridge.send_command(member(9001), "link", {"code": ada["inviteCode"]})
        assert linked["ok"], linked

        # Discord -> web: the message appears in the web chat, with its channel.
        await say_on_discord(bot, link, channel, 9001, "Shall we book the lab for Tuesday?")
        seen = await tab.wait_for(lambda e: e["type"] == "message" and e["message"]["channel"] == "discord")
        assert seen["message"]["author"] == {"id": 0, "name": "Chiara"}
        assert seen["message"]["text"] == "Shall we book the lab for Tuesday?"

        # Web -> Discord: one line with the author's name.
        await tab.send(type="message", text="Tuesday works for me")
        await tab.wait_for(lambda e: e["type"] == "message" and e["message"]["text"] == "Tuesday works for me")
        await until(lambda: "**Ada** · Web: Tuesday works for me" in channel.lines)

        # A card made on the web is posted on Discord and confirmed there.
        await tab.send(type="command", command="kickoff", args={"text": "Deliver by 2 Dec."}, requestId="k1")
        await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "k1" and e["answer"]["ok"])
        card = await tab.wait_for(lambda e: e["type"] == "proposal")
        await until(lambda: len(channel.cards) == 1)
        dario = member(9002)
        await bridge.click(dario, "confirm", card["proposal"]["proposal_id"])
        assert dario.said[-1] == "Confirmed and saved."
        applied = await tab.wait_for(lambda e: e["type"] == "proposal" and e["proposal"]["status"] == "applied")
        assert applied["proposal"]["names"][str(9002)] == "Dario"  # the web can name who confirmed

        # One project: the web panel shows the charter Dario confirmed on Discord.
        state = await tab.wait_for(lambda e: e["type"] == "state" and e["state"].get("charter"))
        assert state["state"]["charter"]["confirmed_by"] == 9002  # small ids stay numbers
        on_discord = await bridge.send_command(member(9001), "state")
        assert on_discord["state"]["charter"]["goal"] == state["state"]["charter"]["goal"]

        # Catch up answers on both sides, and says the group is linked.
        await tab.send(type="command", command="catchup", requestId="u1")
        caught = await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "u1")
        assert caught["answer"]["ok"] and caught["answer"]["catchup"]["linked"] is True
        assert (await bridge.send_command(member(9001), "catchup"))["catchup"]["linked"] is True

        # Unlinked, the channel has its own (empty) plan again.
        assert (await bridge.send_command(member(9001), "unlink"))["ok"]
        assert (await bridge.send_command(member(9001), "state"))["state"]["charter"] is None
    finally:
        await tab.ws.close()
        await bot.registry.close_all()
        SessionRegistry.on_coordinator_event = None


def test_the_words_shared_by_discord_and_slack():
    assert mirror_text({"speakerName": "Ada", "channel": "web", "text": "hi"}) == "**Ada** · Web: hi"
    assert owner_text(9001) == "<@9001>"
    assert owner_text(100_000_001, {"100000001": "Ada"}) == "Ada"
    assert owner_text(100_000_001) == "a Web member" and owner_text(None) == ""
    text = catchup_text({
        "text": "Since your last catch-up: 1 decision, 2 messages on Web.",
        "catchup": {
            "decisions": [{"question": "Which lab slot?", "choice": "Tuesday 17:00", "reason": "Everyone is free"}],
            "elsewhere": [{"channel": "web", "total": 2, "messages": [
                {"speaker": "Ada", "text": "Tuesday?", "at": 0},
                {"speaker": "Bruno", "text": "Yes", "at": 60},
            ]}],
        },
    })
    assert "Decided: Which lab slot? → **Tuesday 17:00** (Everyone is free)" in text
    assert "**On Web**" in text and "Ada: Tuesday?" in text
    assert catchup_text(None).startswith("The coordinator did not answer")
    assert catchup_text({"text": "Nothing new."}) == "Nothing new."
