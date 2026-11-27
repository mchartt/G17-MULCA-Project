"""The harness's real-channel paths, with stand-ins for Discord and Slack (no network)."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import discord

from mulca_discord.coordinator.cards import card_view, proposal_embed

from .harness import DiscordChannel, SlackRecorder

CARD = {"proposal_id": "ab12", "kind": "charter", "status": "pending", "rationale": "r",
        "payload": {"goal": "G", "deliverables": [], "milestones": []}}


class RealDiscord:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, content=None, **kwargs):
        self.sent.append({"content": content, **kwargs})
        edits = self.sent[-1].setdefault("edits", [])

        async def edit(**kw):
            edits.append(kw)

        return SimpleNamespace(edit=edit)


async def test_discord_posts_are_recorded_and_sent_with_no_mentions():
    real = RealDiscord()
    channel = DiscordChannel(42, real)
    await channel.send("hello")
    card = await channel.send(embed=proposal_embed(CARD), view=card_view(CARD))
    await card.edit(embed=proposal_embed({**CARD, "status": "applied"}), view=None)
    assert channel.lines == ["hello"] and channel.cards[0].footer.startswith("✓ Confirmed")
    assert real.sent[0]["allowed_mentions"].everyone is False
    assert isinstance(real.sent[1]["view"], discord.ui.View)
    assert real.sent[1]["edits"][0]["view"] is None


class RealSlack:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def post(self, channel, text, blocks=None):
        self.calls.append(("post", channel, text))
        return f"17000.{len(self.calls)}"

    async def update(self, channel, ts, text, blocks=None):
        self.calls.append(("update", channel, ts, text))


async def test_slack_posts_go_to_the_real_channel_with_its_own_timestamps():
    real = RealSlack()
    slack = SlackRecorder("CFAKE", real, "CREAL")
    ts = await slack.post("CFAKE", "card", [{"type": "context", "elements": [{"type": "mrkdwn", "text": "Waiting"}]}])
    await slack.update("CFAKE", ts, "card", [{"type": "context", "elements": [{"type": "mrkdwn", "text": "✓ Confirmed"}]}])
    await slack.ephemeral("CFAKE", "U0ADA0001", "only you")
    assert real.calls == [("post", "CREAL", "card"), ("update", "CREAL", "17000.1", "card")]
    assert slack.private == [("U0ADA0001", "only you")]  # simulated members have no real account


def test_run_live_tests_finds_the_discord_channel_the_bot_serves(tmp_path, monkeypatch):
    import run_live_tests

    (tmp_path / "data").mkdir()
    with sqlite3.connect(tmp_path / "data" / "mulca.db") as db:
        db.execute("CREATE TABLE links (text_channel_id INTEGER)")
        db.execute("INSERT INTO links VALUES (1573774500464562309)")
    monkeypatch.setattr(run_live_tests, "HERE", tmp_path)
    assert run_live_tests.discord_channel() == "1573774500464562309"
    monkeypatch.setattr(run_live_tests, "HERE", tmp_path / "nowhere")
    assert run_live_tests.discord_channel() == ""
