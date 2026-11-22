"""
The Slack channel (mulca_discord/slack/): ids, the /coordinator text, cards,
and one end-to-end run with a fake Slack against a real local MUCA-Server
(coordinator on, fake model), linked to a web space.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from mulca_discord.slack import SlackHub, ids
from mulca_discord.slack.__main__ import handle
from mulca_discord.slack.cards import ACTION_ID, card_blocks, card_text, to_mrkdwn
from mulca_discord.slack.commands import HELP, Usage, parse, state_text
from mulca_discord.slack.hub import CHANNEL_ONLY
from mulca_discord.web.hub import browser_safe
from tests.test_coordinator_discord import coordinator_server  # noqa: F401  (pytest fixture)
from tests.test_cross_channel import until
from tests.test_web import Tab, web  # noqa: F401  (pytest fixture)

CHIARA, DARIO, BOT = "U07CHIARA01", "U07DARIO002", "U0BOT"


class FakeSlack:
    """Slack as the hub sees it (slack/api.py SlackApi), recording what is posted."""

    bot_user = BOT

    def __init__(self) -> None:
        self.posts: list[dict] = []  # every message, in order; updates change them in place
        self.private: list[tuple[str, str]] = []  # (user, text)

    async def post(self, channel, text, blocks=None) -> str:
        self.posts.append({"channel": channel, "text": text, "blocks": blocks})
        return str(len(self.posts))

    async def update(self, channel, ts, text, blocks=None) -> None:
        self.posts[int(ts) - 1].update(text=text, blocks=blocks)

    async def ephemeral(self, channel, user, text) -> None:
        self.private.append((user, text))

    async def roster(self, channel) -> dict[str, str]:
        return {CHIARA: "Chiara", DARIO: "Dario"}

    def cards(self) -> list[dict]:
        return [p for p in self.posts if p["blocks"]]


# ----------------------------------------------------------------------
# Small pieces
# ----------------------------------------------------------------------


def test_slack_ids_become_integers_no_other_channel_uses_and_back():
    member = ids.member_id(CHIARA)
    assert member >= 2**62 and member < 2**63  # fits SQLite and JSON
    assert ids.slack_user(member) == CHIARA
    assert ids.who(member) == f"<@{CHIARA}>"
    assert ids.who(100_000_001, {"100000001": "Ada"}) == "Ada"  # a web member: by name
    assert ids.who(1_400_000_000_000_000_000) == "a Discord member"
    # The browser gets the big id as text, so it is not rounded.
    assert browser_safe({"owner_id": member, "n": 3, "list": [member]}) == {"owner_id": str(member), "n": 3, "list": [str(member)]}


def test_the_text_after_the_slash_command():
    assert parse("kickoff Deliver by 2 Dec.") == ("kickoff", {"text": "Deliver by 2 Dec."})
    assert parse("planning Server API; UI screens ;") == ("planning", {"text": "Server API\nUI screens"})
    assert parse("task 2 DONE") == ("task", {"task": "2", "status": "done"})
    assert parse("why did we drop it?") == ("why", {"question": "did we drop it?"})
    assert parse("profile HCI | figma, ux | 6") == ("profile", {"discipline": "HCI", "skills": "figma, ux", "weekly_hours": 6})
    assert parse("profile HCI") == ("profile", {"discipline": "HCI", "skills": "", "weekly_hours": None})
    assert parse("link ab12cd please") == ("link", {"code": "ab12cd"})
    assert parse("ask who does the slides?") == ("ask", {"question": "who does the slides?"})
    assert parse(" Plan ") == ("state", {}) and parse("catchup") == ("catchup", {})
    for bad in ("", "dance", "kickoff", "ask", "task two done", "task 2 finished", "profile a | b | many", "link"):
        with pytest.raises(Usage):
            parse(bad)
    with pytest.raises(Usage, match="Coordinator commands"):
        parse("help")
    assert "/coordinator link" in HELP


def test_a_card_has_the_same_content_and_buttons_as_on_discord():
    proposal = {
        "proposal_id": "ab12", "kind": "task_owner", "status": "pending", "rationale": "Stepping in because nobody owns it.",
        "payload": {"title": "Book the lab", "owner_id": ids.member_id(CHIARA), "due_date": "2026-11-24", "context": {"strategy_id": "cs5_owner_and_date"}},
    }
    blocks = card_blocks(proposal)
    text = "\n".join(b["text"]["text"] for b in blocks if b["type"] == "section")
    assert "Coordinator · Owner and date" in text and f"<@{CHIARA}>" in text and "Book the lab" in text
    answers, about = [[e["action_id"] for e in b["elements"]] for b in blocks if b["type"] == "actions"]
    assert answers == ["coord:confirm:ab12", "coord:take:ab12", "coord:reject:ab12"]
    assert about == ["coord:why:ab12", "coord:helpful:ab12", "coord:not_now:ab12"]
    assert all(ACTION_ID.match(a) for a in answers + about)
    assert card_text(proposal).startswith("Coordinator · Owner and date")

    closed = card_blocks({**proposal, "status": "applied"})
    assert not [b for b in closed if b["type"] == "actions"]
    assert closed[-1]["elements"][0]["text"] == "Confirmed"

    decision = card_blocks({"proposal_id": "cd34", "kind": "decision", "status": "pending", "payload": {"question": "Stack?", "options": [{"label": "React"}, {"label": "Vue"}]}})
    assert [e["action_id"] for e in decision[-2]["elements"]] == ["coord:choose0:cd34", "coord:choose1:cd34", "coord:reject:cd34"]
    assert to_mrkdwn("**Ada** said") == "*Ada* said"


def test_the_plan_as_a_private_message():
    text = state_text({
        "charter": {"goal": "Ship it"},
        "tasks": [{"title": "Mockup", "status": "doing", "owner_id": 100_000_001, "due_date": "2026-11-20"}],
        "names": {"100000001": "Ada"},
    })
    assert "Ship it" in text and "1. Mockup · doing · Ada · 2026-11-20" in text
    assert "No charter yet" in state_text({})


# ----------------------------------------------------------------------
# End to end: fake Slack, real MUCA-Server, a linked web space
# ----------------------------------------------------------------------


async def test_slack_alone_then_linked_to_a_web_space(web, coordinator_server):  # noqa: F811
    web_hub, http, ws_url = web
    slack = FakeSlack()
    hub = SlackHub(slack, coordinator_server)
    try:
        # Not in a DM, and a wrong command gets the help.
        assert await hub.on_command("D1", CHIARA, "plan", is_dm=True) == CHANNEL_ONLY
        assert "Coordinator commands" in await hub.on_command("C1", CHIARA, "dance")

        # A message with a mention is for Cadence (as on the web app): "thinking"
        # first, then that same line becomes the coordinator's answer.
        await hub.on_message({"type": "message", "channel": "C1", "user": CHIARA, "text": f"<@{BOT}> hello <@{DARIO}>"})
        await until(lambda: slack.posts and slack.posts[0]["text"] == "Nobody owns the slides yet.")
        assert len(slack.posts) == 1  # the thinking line was replaced, not followed
        # The bot's own posts, edits and DMs are not messages of the group.
        before = len(slack.posts)
        for ignored in ({"bot_id": "B1"}, {"subtype": "message_changed"}, {"channel_type": "im"}, {"user": BOT}):
            await hub.on_message({"type": "message", "channel": "C1", "user": CHIARA, "text": "x", **ignored})
        await asyncio.sleep(0.2)
        assert len(slack.posts) == before

        # Kickoff -> a card with buttons; a click confirms it and the card is updated in place.
        assert "Charter card posted" in await hub.on_command("C1", CHIARA, "kickoff Deliver by 2 Dec.")
        await until(lambda: len(slack.cards()) == 1)
        card = slack.cards()[0]
        confirm = next(e["action_id"] for b in card["blocks"] if b["type"] == "actions" for e in b["elements"] if "confirm" in e["action_id"])
        assert await hub.on_action("C1", DARIO, confirm, "ignored") == "Confirmed and saved."
        await until(lambda: card["blocks"][-1]["elements"][0]["text"] == "Confirmed")
        assert "Ship the coordinator." in await hub.on_command("C1", CHIARA, "plan")
        assert await hub.on_action("C1", "U0STRANGER", confirm) == "Only members of this group can use the coordinator here."
        assert await hub.on_action("C1", DARIO, "coord:dance:zz") == "This button is not known to the coordinator."

        # Link the channel to a web space: the web's (empty) project is now the shared one.
        async with httpx.AsyncClient(base_url=http) as api:
            ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
        tab = await Tab.open(ws_url, ada["token"])
        await tab.send(type="command", command="state", requestId="s0")
        await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "s0")
        assert "Linked to the web space" in await hub.on_command("C1", CHIARA, f"link {ada['inviteCode']}")
        assert "No charter yet" in await hub.on_command("C1", CHIARA, "plan")

        # Slack -> web; not web -> Slack: chat is copied one way only, into the web space (21/11).
        await hub.on_message({"type": "message", "channel": "C1", "user": DARIO, "text": "Lab on Tuesday?"})
        seen = await tab.wait_for(lambda e: e["type"] == "message" and e["message"]["channel"] == "slack")
        assert seen["message"]["author"]["name"] == "Dario" and seen["message"]["text"] == "Lab on Tuesday?"
        await tab.send(type="message", text="Tuesday works")

        # A card made on the web appears on Slack and is confirmed there.
        await tab.send(type="command", command="kickoff", args={"text": "Deliver by 2 Dec."}, requestId="k1")
        await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "k1" and e["answer"]["ok"])
        await until(lambda: len(slack.cards()) == 2)
        assert not any("· Web:" in str(p.get("text", "")) for p in slack.posts)
        shared = next(e["action_id"] for b in slack.cards()[1]["blocks"] if b["type"] == "actions" for e in b["elements"] if "confirm" in e["action_id"])
        assert await hub.on_action("C1", CHIARA, shared) == "Confirmed and saved."
        applied = await tab.wait_for(lambda e: e["type"] == "proposal" and e["proposal"]["status"] == "applied")
        state = await tab.wait_for(lambda e: e["type"] == "state" and e["state"].get("charter"))
        chiara = str(ids.member_id(CHIARA))
        assert state["state"]["charter"]["confirmed_by"] == chiara  # as text: too big for a browser number
        assert applied["proposal"]["names"][chiara] == "Chiara"

        assert "last 7 days" in await hub.on_command("C1", CHIARA, "catchup")  # the first catch-up
        await tab.ws.close()
    finally:
        await hub.close()


async def test_socket_mode_requests_reach_the_hub_and_answer_privately():
    class Hub:
        def __init__(self) -> None:
            self.seen = []

        async def on_message(self, event):
            self.seen.append(("message", event["text"]))

        async def on_command(self, channel, user, text, *, is_dm=False):
            return f"ran {text} dm={is_dm}"

        async def on_action(self, channel, user, action_id, ts=""):
            return f"clicked {action_id} on {ts}"

    hub, slack = Hub(), FakeSlack()
    await handle(hub, slack, "events_api", {"event": {"type": "message", "text": "hi"}})
    await handle(hub, slack, "events_api", {"event": {"type": "reaction_added"}})
    await handle(hub, slack, "slash_commands", {"channel_id": "C1", "user_id": CHIARA, "text": "plan", "channel_name": "team"})
    await handle(hub, slack, "interactive", {
        "type": "block_actions", "channel": {"id": "C1"}, "user": {"id": DARIO},
        "container": {"message_ts": "12.3"}, "actions": [{"action_id": "coord:confirm:ab"}],
    })
    assert hub.seen == [("message", "hi")]
    assert slack.private == [(CHIARA, "ran plan dm=False"), (DARIO, "clicked coord:confirm:ab on 12.3")]
