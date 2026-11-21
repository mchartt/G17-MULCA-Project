"""
Group Coordinator on Discord: cards, commands, switch, bridge, and one
end-to-end run against a real local MUCA-Server with the coordinator on
(the model is a fake, nothing leaves the machine).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import discord
import pytest
import uvicorn
from discord import app_commands

from muca_server import create_app
from muca_server.cognition.coordination.settings import CoordinatorSettings
from muca_server.cognition.coordination.wiring import build_coordinator_factory
from muca_server.sessions import DefaultSessionComponentsFactory

from mulca_discord.coordinator.bridge import NO_ANSWER, NOT_LINKED, CoordinatorBridge, answer_text
from mulca_discord.coordinator.cards import CardButton, card_view, proposal_embed
from mulca_discord.coordinator.commands import (
    CoordinatorGroup,
    coordinator_enabled,
    install_coordinator,
    state_embed,
)
from mulca_discord.muca_client import MucaWsClient
from mulca_discord.sessions import SessionRegistry

from tests.test_muca_client import AnswerEverything, Factory, free_port

PENDING = {
    "proposal_id": "abc123",
    "kind": "charter",
    "status": "pending",
    "payload": {
        "goal": "Ship the coordinator.",
        "deliverables": ["Report", "Prototype"],
        "milestones": [{"title": "Demo", "due_date": "2026-12-02"}, {"title": "Pitch", "due_date": None}],
    },
    "rationale": "Stepping in because you pasted the assignment.",
    "expires_at": 1_800_000_000.0,
}
CHARTER = {
    "goal": "Ship the coordinator.",
    "deliverables": ["Report"],
    "milestones": [{"title": "Demo", "due_date": "2026-12-02"}],
    "rationale": "Stepping in because you pasted the assignment.",
}


# ----------------------------------------------------------------------
# Cards
# ----------------------------------------------------------------------


def test_a_pending_card_shows_reason_content_status_and_two_buttons():
    embed = proposal_embed(PENDING)
    assert embed.title == "Coordinator · Project charter"
    assert embed.description == "*Stepping in because you pasted the assignment.*"
    fields = {f.name: f.value for f in embed.fields}
    assert fields["Goal"] == "Ship the coordinator."
    assert fields["Deliverables"] == "• Report\n• Prototype"
    assert fields["Milestones"] == "• Demo — 2026-12-02\n• Pitch — no date"
    assert embed.footer.text.startswith("Waiting for a member to confirm · expires")
    ids = [item.item.custom_id for item in card_view(PENDING).children]
    assert ids == ["coord:confirm:abc123", "coord:reject:abc123"]


@pytest.mark.parametrize("status,words", [("applied", "Confirmed"), ("rejected", "Rejected"), ("expired", "Expired")])
def test_a_closed_card_says_so_in_words_and_has_no_buttons(status, words):
    closed = dict(PENDING, status=status)
    assert proposal_embed(closed).footer.text == words
    assert card_view(closed) is None


def test_long_fields_are_cut_to_what_discord_accepts():
    long = dict(PENDING, payload=dict(PENDING["payload"], goal="x" * 5000))
    assert len(proposal_embed(long).fields[0].value) == 1000


async def test_a_button_is_rebuilt_from_its_custom_id():
    import re

    from mulca_discord.coordinator.cards import CUSTOM_ID_PATTERN

    match = re.fullmatch(CUSTOM_ID_PATTERN, "coord:reject:abc123")
    button = await CardButton.from_custom_id(None, None, match)
    assert (button.action, button.proposal_id) == ("reject", "abc123")
    assert re.fullmatch(CUSTOM_ID_PATTERN, "coord:delete:abc123") is None


async def test_a_click_with_the_coordinator_off_says_so():
    CardButton.bridge = None
    sent = []
    interaction = SimpleNamespace(
        response=SimpleNamespace(send_message=lambda text, ephemeral: _record(sent, text))
    )
    await CardButton("confirm", "abc123").callback(interaction)
    assert sent == ["The coordinator is off."]


async def _record(sink, value):
    sink.append(value)


# ----------------------------------------------------------------------
# Switch and commands
# ----------------------------------------------------------------------


def test_the_switch_is_off_by_default():
    assert not coordinator_enabled({})
    assert coordinator_enabled({"MULCA_COORDINATOR_ENABLED": "yes"})


def test_off_installs_nothing():
    tree = SimpleNamespace(add_command=lambda group: pytest.fail("must not add"))
    assert install_coordinator(SimpleNamespace(), tree, env={}) is None


def test_on_installs_the_group_the_buttons_and_the_event_hook():
    registry = SimpleNamespace(on_coordinator_event=None)
    added_items = []
    client = SimpleNamespace(add_dynamic_items=lambda *items: added_items.extend(items))
    manager = SimpleNamespace(bots=[SimpleNamespace(registry=registry)], primary=SimpleNamespace(client=client))
    groups = []
    tree = SimpleNamespace(add_command=groups.append)

    bridge = install_coordinator(manager, tree, env={"MULCA_COORDINATOR_ENABLED": "1"})

    assert isinstance(bridge, CoordinatorBridge)
    assert SessionRegistry.on_coordinator_event == bridge.on_event
    assert added_items == [CardButton] and CardButton.bridge is bridge
    (group,) = groups
    assert isinstance(group, CoordinatorGroup) and group.name == "coordinator"
    assert sorted(c.name for c in group.commands) == ["ask", "catchup", "checkin", "kickoff", "link", "me", "plan", "planning", "profile", "task", "unlink", "why"]
    CardButton.bridge = None
    SessionRegistry.on_coordinator_event = None


def test_the_plan_embed_lists_every_part_of_the_state():
    embed = state_embed(
        {
            "charter": {"goal": "G"},
            "milestones": [{"title": "Demo", "due_date": None}],
            "members": [{"display_name": "Ada", "discipline": "CS"}],
            "tasks": [{"title": "Mockup", "status": "doing"}],
            "decisions": [{"question": "Stack?", "choice": "React"}],
        }
    )
    assert [f.value for f in embed.fields] == ["G", "• Demo — no date", "• Ada · CS", "• 1. Mockup · doing", "• Stack? → React"]
    assert state_embed({}).fields[0].value.startswith("No charter yet")


def test_answer_text():
    assert answer_text(None) == NO_ANSWER
    assert answer_text({"event": "coordinator_notice", "ok": True, "text": "Saved."}) == "Saved."
    assert answer_text({"event": "coordinator_state"}) == "Done."


async def test_a_command_with_no_bot_running_or_in_a_dm_is_refused():
    manager = SimpleNamespace(bots=[], link_for_channel=lambda channel_id: None)
    interaction = SimpleNamespace(channel_id=5, user=SimpleNamespace(id=1))
    answer = await CoordinatorBridge(manager).send_command(interaction, "state")
    assert answer["text"] == NOT_LINKED
    # A direct message has no server: nothing is linked.
    bot = SimpleNamespace(user_id=9, store=None)
    manager = SimpleNamespace(bots=[bot], primary=bot, link_for_channel=lambda channel_id: None)
    dm = SimpleNamespace(channel_id=5, channel=SimpleNamespace(id=5), guild_id=None, user=SimpleNamespace(id=1))
    assert (await CoordinatorBridge(manager).send_command(dm, "state"))["text"] == NOT_LINKED


async def test_the_first_coordinator_command_makes_the_bot_serve_the_channel():
    """One step, as on Slack: no /mulca link first (21/11)."""
    saved, applied = [], []

    class Store:
        def conflicts(self, link):
            return []

        def save(self, link, *, created_by=None):
            saved.append((link, created_by))
            return None

    async def apply_link(link, previous):
        applied.append((link, previous))

    bot = SimpleNamespace(user_id=9, store=Store(), apply_link=apply_link)
    # Still not found after saving: the command then answers NOT_LINKED, which
    # shows the bridge went on to send it (the real manager finds the new link).
    manager = SimpleNamespace(bots=[bot], primary=bot, link_for_channel=lambda channel_id: None)
    interaction = SimpleNamespace(channel_id=42, channel=SimpleNamespace(id=42), guild_id=7, user=SimpleNamespace(id=1))
    answer = await CoordinatorBridge(manager).send_command(interaction, "link", {"code": "ABCDEFGHJK"})
    ((link, created_by),) = saved
    assert (link.text_channel_id, link.guild_id, link.bot_id, link.voice_channel_id, link.listening_mode) == (42, 7, 9, None, "")
    assert created_by == 1 and applied == [(link, None)]
    assert answer["text"] == NOT_LINKED


async def test_a_channel_that_cannot_be_served_says_why():
    class Store:
        def conflicts(self, link):
            return ["This voice channel is already linked."]

    bot = SimpleNamespace(user_id=9, store=Store())
    manager = SimpleNamespace(bots=[bot], primary=bot, link_for_channel=lambda channel_id: None)
    interaction = SimpleNamespace(channel_id=42, channel=SimpleNamespace(id=42), guild_id=7, user=SimpleNamespace(id=1))
    answer = await CoordinatorBridge(manager).send_command(interaction, "state")
    assert answer["ok"] is False and answer["text"].startswith("Cadence cannot work in this channel:")


# ----------------------------------------------------------------------
# The client routes the three server events, and only those
# ----------------------------------------------------------------------


async def test_the_client_hands_coordinator_events_to_its_hook():
    client = MucaWsClient("ws://unused/", conversation_id="channel:1", is_dm=False)
    seen = []

    async def hook(data):
        seen.append(data["event"])

    client.on_coordinator_event = hook
    for event in ("coordinator_proposal", "coordinator_state", "coordinator_notice", "agent_message"):
        await client._handle_raw(json.dumps({"event": event}))
    assert seen == ["coordinator_proposal", "coordinator_state", "coordinator_notice"]


# ----------------------------------------------------------------------
# End to end: real MUCA-Server (coordinator on) + real client and registry
# ----------------------------------------------------------------------


# A question to Cadence (the "ask" command) gets this answer.
ASK_ANSWER = {"answer": "Nobody owns the slides yet.", "task_ids": [], "milestone_ids": [], "decision_ids": [], "documents": []}


class FakeChat:
    """The model: answers a question to Cadence with ASK_ANSWER, anything else with CHARTER."""

    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        schema = kwargs.get("response_format", {}).get("json_schema", {}).get("name")
        answer = ASK_ANSWER if schema == "project_answer" else CHARTER
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(answer)))],
            usage=None,
        )


class Channel:
    """A Discord text channel that records cards and their edits."""

    def __init__(self) -> None:
        self.cards: list[dict] = []

    async def send(self, content=None, *, embed=None, view=None):
        channel = self

        class Message:
            async def edit(self, *, embed, view):
                channel.cards.append({"footer": embed.footer.text, "buttons": view is not None})

        self.cards.append({"footer": embed.footer.text, "buttons": view is not None and view is not discord.utils.MISSING})
        return Message()


@pytest.fixture
async def coordinator_server(tmp_path):
    port = free_port()
    app = create_app(
        components_factory=DefaultSessionComponentsFactory(
            agent_factory=Factory(),
            policy_factory=lambda context: AnswerEverything(),
            coordinator_factory=build_coordinator_factory(
                CoordinatorSettings(enabled=True), client=FakeChat(), db_dir=str(tmp_path)
            ),
        )
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    yield f"ws://127.0.0.1:{port}/"
    server.should_exit = True
    await task


async def test_kickoff_card_and_confirm_end_to_end(coordinator_server):
    channel = Channel()
    registry = SessionRegistry(coordinator_server)
    link = SimpleNamespace(
        conversation_id="channel:42", listening_mode="", guild_id=1, text_channel_id=42
    )
    bot = SimpleNamespace(
        name="MULCA",
        registry=registry,
        roster_text=lambda link: {1: "Ada", 2: "Bruno"},
        _channel_name_for=lambda link: "group-17",
        course_for=lambda guild_id: "aui",
        client=SimpleNamespace(
            get_channel=lambda channel_id: channel,
            add_dynamic_items=lambda *items: registered.extend(items),
        ),
    )
    registered = []
    manager = SimpleNamespace(bots=[bot], link_for_channel=lambda channel_id: (bot, link))
    bridge = CoordinatorBridge(manager)
    bridge.attach()

    member = SimpleNamespace(channel_id=42, user=SimpleNamespace(id=2))
    answer = await bridge.send_command(member, "kickoff", {"text": "Deliver by 2 Dec."})
    assert answer["ok"], answer
    assert channel.cards == [{"footer": channel.cards[0]["footer"], "buttons": True}]
    proposal_id = next(iter(bridge._cards))

    followups = []
    click = SimpleNamespace(
        channel_id=42,
        user=SimpleNamespace(id=1),
        response=SimpleNamespace(defer=lambda **kw: _record(followups, "deferred")),
        followup=SimpleNamespace(send=lambda text, ephemeral: _record(followups, text)),
    )
    await bridge.click(click, "confirm", proposal_id)
    assert followups == ["deferred", "Confirmed and saved."]
    assert channel.cards[-1] == {"footer": "Confirmed", "buttons": False}

    state = await bridge.send_command(member, "state")
    assert state["state"]["charter"]["goal"] == "Ship the coordinator."
    assert state["state"]["charter"]["confirmed_by"] == 1

    # Someone outside the roster cannot click any more (and could not before).
    outsider = SimpleNamespace(**{**click.__dict__, "user": SimpleNamespace(id=99)})
    followups.clear()
    await bridge.click(outsider, "reject", proposal_id)
    assert followups[-1] == "Only members of this group can use the coordinator here."
    # The bot that posted the card has the button class registered (once).
    assert registered == [CardButton]
    await registry.close_all()
    SessionRegistry.on_coordinator_event = None


# ----------------------------------------------------------------------
# The three command callbacks, with a fake bridge
# ----------------------------------------------------------------------


class FakeBridge:
    def __init__(self, answer) -> None:
        self.answer = answer
        self.sent: list[tuple[str, dict | None]] = []

    async def send_command(self, interaction, command, args=None):
        self.sent.append((command, args))
        return self.answer


def an_interaction(record):
    return SimpleNamespace(
        response=SimpleNamespace(defer=lambda **kw: _record(record, ("defer", kw))),
        followup=SimpleNamespace(send=lambda *a, **kw: _record(record, (a, kw))),
    )


async def test_profile_and_kickoff_send_their_arguments_and_answer_privately():
    notice = {"event": "coordinator_notice", "ok": True, "text": "Profile saved."}
    bridge, record = FakeBridge(notice), []
    group = CoordinatorGroup(bridge)

    await group.profile.callback(group, an_interaction(record), "Design", "figma", 5)
    await group.kickoff.callback(group, an_interaction(record), "Deliver by 2 Dec.")

    assert bridge.sent == [
        ("profile", {"discipline": "Design", "skills": "figma", "weekly_hours": 5}),
        ("kickoff", {"text": "Deliver by 2 Dec."}),
    ]
    assert record[0] == ("defer", {"ephemeral": True, "thinking": True})
    assert record[1] == (("Profile saved.",), {"ephemeral": True})


async def test_plan_shows_the_state_embed_or_explains_why_not():
    record = []
    group = CoordinatorGroup(FakeBridge({"event": "coordinator_state", "state": {}}))
    await group.plan.callback(group, an_interaction(record))
    assert record[1][1]["embed"].title == "Coordinator · Project plan"

    record.clear()
    group = CoordinatorGroup(FakeBridge(None))
    await group.plan.callback(group, an_interaction(record))
    assert record[1] == ((NO_ANSWER,), {"ephemeral": True})


# ----------------------------------------------------------------------
# Bridge error paths
# ----------------------------------------------------------------------


def a_bridge_whose_server(run):
    link = SimpleNamespace(conversation_id="channel:42", listening_mode="", guild_id=1, text_channel_id=42)
    bot = SimpleNamespace(
        name="MULCA",
        registry=SimpleNamespace(run=run, on_coordinator_event=None),
        roster_text=lambda link: {1: "Ada"},
        _channel_name_for=lambda link: "g",
        course_for=lambda guild_id: "aui",
        client=SimpleNamespace(get_channel=lambda channel_id: None, add_dynamic_items=lambda *i: None),
    )
    return CoordinatorBridge(SimpleNamespace(bots=[bot], link_for_channel=lambda cid: (bot, link)))


async def test_a_server_that_never_answers_gives_no_answer(monkeypatch):
    import mulca_discord.coordinator.bridge as bridge_module

    monkeypatch.setattr(bridge_module, "ANSWER_TIMEOUT_SECONDS", 0.05)

    async def run(scope, action, **kwargs):
        pass  # sent, but the server stays silent

    bridge = a_bridge_whose_server(run)
    member = SimpleNamespace(channel_id=42, user=SimpleNamespace(id=1))
    assert await bridge.send_command(member, "state") is None
    assert bridge._waiting == {}  # nothing left waiting


async def test_a_lost_connection_gives_no_answer_and_does_not_raise():
    async def run(scope, action, **kwargs):
        raise ConnectionError("server down")

    bridge = a_bridge_whose_server(run)
    member = SimpleNamespace(channel_id=42, user=SimpleNamespace(id=1))
    assert await bridge.send_command(member, "state") is None


async def test_a_closed_card_never_posted_is_not_posted_now():
    channel = Channel()
    session = SimpleNamespace(replies=SimpleNamespace(channel=channel))
    await CoordinatorBridge(SimpleNamespace(bots=[])).on_event(
        session, {"event": "coordinator_proposal", "proposal": dict(PENDING, status="applied")}
    )
    assert channel.cards == []


async def test_a_card_discord_refuses_is_logged_not_raised():
    class Refusing:
        async def send(self, **kwargs):
            raise discord.HTTPException(SimpleNamespace(status=403, reason="Forbidden"), "no perms")

    session = SimpleNamespace(replies=SimpleNamespace(channel=Refusing()))
    await CoordinatorBridge(SimpleNamespace(bots=[])).on_event(
        session, {"event": "coordinator_proposal", "proposal": PENDING}
    )


def test_a_registry_created_after_attach_still_gets_the_events():
    """Bots added later with /mulca bot add get new registries."""
    bridge = CoordinatorBridge(SimpleNamespace(bots=[]))
    bridge.attach()
    later = SessionRegistry("ws://unused/")
    assert later.on_coordinator_event == bridge.on_event
    SessionRegistry.on_coordinator_event = None
