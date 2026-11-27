"""
The demo video, as a test: one project on the web, Discord and Slack.

Frames of the video (Nov 2026):
  1. Discord, #presentation: Cadence posts "Cadence · Owner and date · Ownership"
     (task, by, suggested owner); Ada takes it there.
  2. Slack, #school-talk: the same card, now "✓ Confirmed"; Bruno writes
     "oh nice, Ada took it on Discord".
  3. Web: the card "Confirmed by Ada", and the Discord and Slack messages in
     the group chat with their channel tag.

The web space is the hub: it holds the project and sees every channel's
chat. A card reaches every linked channel that is open, so the Slack and
Discord sessions open when the bot starts (warm_up), not at the first message.
"""

from __future__ import annotations

import httpx

from mulca_discord.coordinator.cards import card_view, proposal_embed
from mulca_discord.slack import SlackHub
from mulca_discord.slack.cards import card_blocks
from mulca_discord.sessions import SessionRegistry
from tests.test_coordinator_discord import coordinator_server  # noqa: F401  (pytest fixture)
from tests.test_cross_channel import discord_side, member, say_on_discord, until
from tests.test_slack import CHIARA, DARIO, FakeSlack
from tests.test_web import Tab, web  # noqa: F401  (pytest fixture)

ADA = 9001  # on Discord (discord_side's roster names 9001 "Chiara": the ids are what matter)

# The card of the video, as MUCA-Server sends it (CS5, owner and date).
VIDEO_CARD = {
    "proposal_id": "c5a1",
    "kind": "task_owner",
    "status": "pending",
    "rationale": "Printing the survey results came up, but nobody took it.",
    "payload": {
        "title": "Print the survey results",
        "due_date": "28 Nov",
        "owner_id": 100000123,  # a web member: written by name on every channel
        "context": {"strategy_id": "cs5_owner_and_date", "topic": "printing", "evidence": []},
    },
    "names": {"100000123": "Ada"},
}


def test_the_video_card_reads_the_same_on_discord_and_slack():
    embed = proposal_embed(VIDEO_CARD)
    assert embed.title == "Cadence · Owner and date · Ownership"
    assert embed.description == "*Printing the survey results came up, but nobody took it.*"
    assert [(f.name, f.value) for f in embed.fields] == [
        ("Task", "Print the survey results"),
        ("By", "28 Nov"),
        ("Suggested owner", "Ada"),
    ]
    blocks = card_blocks(VIDEO_CARD)
    texts = [b["text"]["text"] for b in blocks if b["type"] == "section"]
    assert texts == [
        "*Cadence · Owner and date · Ownership*\n_Printing the survey results came up, but nobody took it._",
        "*Task*\nPrint the survey results",
        "*By*\n28 Nov",
        "*Suggested owner*\nAda",
    ]

    # Ada took it: both say so, with her name, and the buttons are gone.
    done = {**VIDEO_CARD, "status": "applied", "resolved_by": 100000123}
    assert proposal_embed(done).footer.text == "✓ Confirmed by Ada"
    assert card_view(done) is None
    closed = card_blocks(done)
    assert closed[-1] == {"type": "context", "elements": [{"type": "mrkdwn", "text": "✓ Confirmed by Ada"}]}
    assert not [b for b in closed if b["type"] == "actions"]


async def test_a_card_confirmed_on_discord_is_confirmed_on_slack_and_the_web(web, coordinator_server):  # noqa: F811
    _, http, ws_url = web
    async with httpx.AsyncClient(base_url=http) as api:
        space = (await api.post("/api/groups", json={"groupName": "Group 17", "displayName": "Bruno"})).json()
    tab = await Tab.open(ws_url, space["token"])
    await tab.send(type="command", command="state", requestId="s0")
    await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "s0")

    bridge, bot, link, discord_channel = discord_side(coordinator_server)
    slack = FakeSlack()
    first = SlackHub(slack, coordinator_server)
    later = None
    try:
        # Both channels are linked to the web space with its invite code.
        assert (await bridge.send_command(member(ADA), "link", {"code": space["inviteCode"]}))["ok"]
        assert "Linked to the web space" in await first.on_command("C1", CHIARA, f"link {space['inviteCode']}")

        # The Slack channel restarts and nobody writes there: warm_up opens its session.
        await first.close()
        later = SlackHub(slack, coordinator_server)
        assert await later.warm_up() == ["C1"]

        # A card of the group reaches Discord and Slack at once.
        await tab.send(type="command", command="kickoff", args={"text": "Deliver by 2 Dec."}, requestId="k1")
        await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "k1" and e["answer"]["ok"])
        card = await tab.wait_for(lambda e: e["type"] == "proposal")
        await until(lambda: len(discord_channel.cards) == 1 and len(slack.cards()) == 1)

        # Chat from Discord and Slack lands in the web space, with its channel tag.
        await say_on_discord(bot, link, discord_channel, ADA, "we also need the results printed for the charts")
        await later.on_message({"type": "message", "channel": "C1", "user": DARIO, "text": "anything left for me before Monday?"})
        for tag, said in (("discord", "we also need the results printed for the charts"), ("slack", "anything left for me before Monday?")):
            seen = await tab.wait_for(lambda e, tag=tag: e["type"] == "message" and e["message"].get("channel") == tag)
            assert seen["message"]["text"] == said

        # Confirmed on Discord: the first valid click wins, everywhere.
        clicker = member(ADA)
        await bridge.click(clicker, "confirm", card["proposal"]["proposal_id"])
        assert clicker.said[-1] == "Confirmed and saved."
        applied = await tab.wait_for(lambda e: e["type"] == "proposal" and e["proposal"]["status"] == "applied")
        assert str(applied["proposal"]["resolved_by"]) == str(ADA)
        on_slack = slack.cards()[0]
        await until(lambda: on_slack["blocks"][-1]["elements"][0]["text"] == "✓ Confirmed by Chiara (Discord)")
        assert not [b for b in on_slack["blocks"] if b["type"] == "actions"]  # no buttons left on Slack
        await until(lambda: discord_channel.cards[-1] == "✓ Confirmed by Chiara (Discord)")

        # A late click on Slack changes nothing: the card was already answered.
        late = next(
            e["action_id"] for b in card_blocks(card["proposal"]) if b["type"] == "actions" for e in b["elements"] if "confirm" in e["action_id"]
        )
        assert "Confirmed and saved." != await later.on_action("C1", DARIO, late)
    finally:
        await tab.ws.close()
        await bot.registry.close_all()
        if later is not None:
            await later.close()
        SessionRegistry.on_coordinator_event = None


async def test_tasks_and_dependencies_made_on_discord_and_slack_are_on_the_web(web, coordinator_server):  # noqa: F811
    """What happens on Discord or Slack is saved in the web space's project, live."""
    _, http, ws_url = web
    async with httpx.AsyncClient(base_url=http) as api:
        space = (await api.post("/api/groups", json={"groupName": "Group 17", "displayName": "Bruno"})).json()
    tab = await Tab.open(ws_url, space["token"])
    await tab.send(type="command", command="state", requestId="s0")
    await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "s0")

    bridge, bot, link, _ = discord_side(coordinator_server)
    slack = FakeSlack()
    hub = SlackHub(slack, coordinator_server)
    try:
        assert (await bridge.send_command(member(ADA), "link", {"code": space["inviteCode"]}))["ok"]
        assert "Linked" in await hub.on_command("C1", CHIARA, f"link {space['inviteCode']}")

        # Discord: two tasks, the second waits on the first.
        from mulca_discord.coordinator.commands import task_args

        args, problem = task_args(None, None, None, "2026-11-28")
        assert not problem
        assert (await bridge.send_command(member(ADA), "task", {"add": "Collect the paper forms", **args}))["ok"]
        args, problem = task_args(None, None, "1", None)
        assert (await bridge.send_command(member(ADA), "task", {"add": "Print the survey results", **args}))["ok"]

        # Slack: a third task, then it waits on both, then it is being done.
        assert "Task added" in await hub.on_command("C1", DARIO, "task add Make the charts")
        assert "Not done" not in await hub.on_command("C1", DARIO, "task 3 waits on 1, 2")
        assert "Not done" not in await hub.on_command("C1", DARIO, "task 3 doing")

        def done(e):
            tasks = e["type"] == "state" and e["state"].get("tasks") or []
            return len(tasks) == 3 and tasks[2]["status"] == "doing"

        state = (await tab.wait_for(done))["state"]
        first, second, third = state["tasks"]
        assert [t["title"] for t in state["tasks"]] == ["Collect the paper forms", "Print the survey results", "Make the charts"]
        assert first["due_date"] == "2026-11-28"
        assert second["depends_on"] == [first["task_id"]]
        assert sorted(third["depends_on"]) == sorted([first["task_id"], second["task_id"]])

        # The plan reads the same on Discord: one project.
        on_discord = (await bridge.send_command(member(ADA), "state"))["state"]
        assert [t["task_id"] for t in on_discord["tasks"]] == [t["task_id"] for t in state["tasks"]]
    finally:
        await tab.ws.close()
        await bot.registry.close_all()
        await hub.close()
        SessionRegistry.on_coordinator_event = None
