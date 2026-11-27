"""
M3 on Discord: proactive cards (task_owner, delegation, decision), their
buttons, "Why?" and "Not now", and one end-to-end click against a real
local MUCA-Server (coordinator on, model faked, nothing leaves the machine).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from muca_server.cognition.coordination.models import ProposalKind
from muca_server.cognition.coordination.proposals import ProposalService
from muca_server.cognition.coordination.store import CoordinationStore
from muca_server.cognition.memory.sqlite import db_path_for

from mulca_discord.coordinator.bridge import CoordinatorBridge
from mulca_discord.coordinator.cards import (
    CUSTOM_ID_PATTERN,
    CardButton,
    card_view,
    proposal_embed,
    split_action,
    why_text,
)
from mulca_discord.sessions import SessionRegistry

from tests.test_coordinator_discord import Channel, _record, coordinator_server  # noqa: F401

CONTEXT = {
    "strategy_id": "cs2_delegate_simple_task",
    "topic": "Fonts and margins",
    "evidence": [{"speaker": "Ada", "text": "Arial or Helvetica?", "at_ms": 1}],
}
DELEGATION = {
    "proposal_id": "d1",
    "kind": "delegation",
    "status": "pending",
    "payload": {"context": CONTEXT, "title": "Fix the fonts", "due_date": None, "return_to": "Evaluation protocol",
                "task_id": None, "owner_id": None},
    "rationale": "Stepping in because one person can do this.",
}
TASK = dict(DELEGATION, proposal_id="a1", kind="task_owner",
            payload=dict(DELEGATION["payload"], owner_id=42, due_date="2026-11-27", return_to=""))
DECISION = {
    "proposal_id": "c1",
    "kind": "decision",
    "status": "pending",
    "payload": {
        "context": dict(CONTEXT, strategy_id="cs3_close_decision", topic="Test method"),
        "question": "Which usability test?",
        "options": [{"label": "Think-aloud", "argument": "Shows why users get stuck."},
                    {"label": "SUS", "argument": "Fast, only a score."}],
    },
    "rationale": "Stepping in because the choice is open.",
}


def ids(view):
    return [item.item.custom_id for item in view.children]


def test_delegation_card_never_names_an_owner_and_offers_take():
    embed = proposal_embed(DELEGATION)
    assert embed.title == "Cadence · One person can do this · Ownership"
    fields = {f.name: f.value for f in embed.fields}
    assert fields == {"Task": "Fix the fonts", "By": "no date yet", "Then back to": "Evaluation protocol"}
    assert ids(card_view(DELEGATION)) == ["coord:take:d1", "coord:reject:d1", "coord:why:d1", "coord:helpful:d1", "coord:not_now:d1"]


def test_task_owner_card_suggests_with_a_mention_and_can_be_confirmed():
    fields = {f.name: f.value for f in proposal_embed(TASK).fields}
    assert fields["Suggested owner"] == "<@42>" and fields["By"] == "2026-11-27"
    assert ids(card_view(TASK))[:3] == ["coord:confirm:a1", "coord:take:a1", "coord:reject:a1"]
    no_owner = dict(TASK, payload=dict(TASK["payload"], owner_id=None))
    assert "coord:confirm:a1" not in ids(card_view(no_owner))


def test_decision_card_has_one_button_per_option_then_why_and_not_now_on_row_two():
    view = card_view(DECISION)
    assert ids(view) == [
        "coord:choose0:c1", "coord:choose1:c1", "coord:reject:c1",
        "coord:why:c1", "coord:helpful:c1", "coord:not_now:c1",
    ]
    labels = [item.item.label for item in view.children]
    assert labels[:2] == ["Think-aloud", "SUS"]
    assert [item.item.row for item in view.children][-3:] == [1, 1, 1]
    options = {f.name: f.value for f in proposal_embed(DECISION).fields}["Options"]
    assert "**1. Think-aloud** — Shows why users get stuck." in options


def test_a_snoozed_card_says_so_and_has_no_buttons():
    snoozed = dict(DELEGATION, status="snoozed")
    assert proposal_embed(snoozed).footer.text.startswith("◷ Not now")
    assert card_view(snoozed) is None


async def test_new_custom_ids_rebuild_and_split():
    match = re.fullmatch(CUSTOM_ID_PATTERN, "coord:choose2:c1")
    button = await CardButton.from_custom_id(None, SimpleNamespace(label="SUS"), match)
    assert (button.action, button.proposal_id) == ("choose2", "c1")
    assert split_action("choose2") == ("choose", 2) and split_action("take") == ("take", None)
    assert re.fullmatch(CUSTOM_ID_PATTERN, "coord:choose3:c1") is None


def test_why_shows_strategy_topic_and_the_messages():
    text = why_text(DELEGATION)
    assert text.startswith("Delegate simple tasks (CS2)")
    assert "Topic: Fonts and margins" in text and "> **Ada**: Arial or Helvetica?" in text
    assert why_text({"payload": {"goal": "x"}}) == "This card was asked for by a member of the group."


async def test_why_answers_privately_from_the_card_it_saw():
    bridge = CoordinatorBridge(SimpleNamespace())
    bridge._proposals["d1"] = DELEGATION
    sent = []
    interaction = SimpleNamespace(response=SimpleNamespace(send_message=lambda text, ephemeral: _record(sent, (text, ephemeral))))
    await bridge.why(interaction, "d1")
    assert sent[0][1] is True and "Fonts and margins" in sent[0][0]


def _deferred_interaction(sent):
    async def defer(**_):
        sent.append("deferred")

    return SimpleNamespace(
        response=SimpleNamespace(defer=defer),
        followup=SimpleNamespace(send=lambda text, ephemeral: _record(sent, (text, ephemeral))),
    )


async def test_why_after_a_restart_asks_the_server_for_the_card():
    bridge = CoordinatorBridge(SimpleNamespace())
    asked = []

    async def send_command(interaction, command, args=None):
        asked.append((command, args))
        return {"event": "coordinator_notice", "ok": True, "text": "", "proposal": DELEGATION}

    bridge.send_command = send_command
    sent = []
    await bridge.why(_deferred_interaction(sent), "d1")
    assert asked == [("card", {"proposal_id": "d1"})]
    assert sent[0] == "deferred" and "Fonts and margins" in sent[1][0] and sent[1][1] is True
    assert bridge._proposals["d1"] is DELEGATION  # next time from memory


async def test_why_for_a_card_the_server_does_not_know_says_so():
    bridge = CoordinatorBridge(SimpleNamespace())

    async def refused(interaction, command, args=None):
        return {"event": "coordinator_notice", "ok": False, "text": "That card is not in this group."}

    async def silent(interaction, command, args=None):
        return None

    sent = []
    bridge.send_command = refused
    await bridge.why(_deferred_interaction(sent), "zz")
    bridge.send_command = silent
    await bridge.why(_deferred_interaction(sent), "zz")
    assert sent[1][0] == "That card is not in this group." and "still working" in sent[3][0]


async def test_a_button_passes_its_option_to_the_bridge():
    calls = []

    class Bridge:
        async def click(self, interaction, action, proposal_id, *, option=None):
            calls.append((action, proposal_id, option))

        async def why(self, interaction, proposal_id):
            calls.append(("why", proposal_id))

    CardButton.bridge = Bridge()
    try:
        await CardButton("choose1", "c1").callback(None)
        await CardButton("not_now", "c1").callback(None)
        await CardButton("why", "c1").callback(None)
        await CardButton("helpful", "c1").callback(None)
    finally:
        CardButton.bridge = None
    assert calls == [("choose", "c1", 1), ("not_now", "c1", None), ("why", "c1"), ("helpful", "c1", None)]


async def test_choose_on_discord_records_the_decision_end_to_end(coordinator_server, tmp_path):  # noqa: F811
    # A proactive card the server made earlier (as proactive.py would).
    store = CoordinationStore(db_path_for("channel:42", base_dir=str(tmp_path)))
    from muca_server.cognition.coordination.models import DecisionPayload

    card = await ProposalService(store).create(
        ProposalKind.DECISION, DecisionPayload.model_validate(DECISION["payload"]),
        rationale="Stepping in because.", origin_channel="group",
    )
    channel = Channel()
    registry = SessionRegistry(coordinator_server)
    link = SimpleNamespace(conversation_id="channel:42", listening_mode="", guild_id=1, text_channel_id=42)
    bot = SimpleNamespace(
        name="MULCA", registry=registry, roster_text=lambda link: {1: "Ada", 2: "Bruno"},
        _channel_name_for=lambda link: "group-17", course_for=lambda guild_id: "aui",
        client=SimpleNamespace(get_channel=lambda channel_id: channel, add_dynamic_items=lambda *items: None),
    )
    bridge = CoordinatorBridge(SimpleNamespace(link_for_channel=lambda channel_id: (bot, link)))
    bridge.attach()
    try:
        followups = []
        click = SimpleNamespace(
            channel_id=42, user=SimpleNamespace(id=2),
            response=SimpleNamespace(defer=lambda **kw: _record(followups, "deferred")),
            followup=SimpleNamespace(send=lambda text, ephemeral: _record(followups, text)),
        )
        await bridge.click(click, "choose", card.proposal_id, option=0)
        assert followups == ["deferred", "Decision saved: Think-aloud."]
        (decision,) = (await store.load_state()).decisions
        assert (decision.choice, decision.decided_by) == ("Think-aloud", 2)
        assert decision.source == f"proposal:{card.proposal_id}"
    finally:
        await registry.close_all()
        SessionRegistry.on_coordinator_event = None
