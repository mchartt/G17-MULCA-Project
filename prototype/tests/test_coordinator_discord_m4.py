"""M4 on Discord: /coordinator planning, checkin, task, why, and the plan, checkin and blocker cards."""

from __future__ import annotations

from mulca_discord.coordinator.cards import card_view, proposal_embed
from mulca_discord.coordinator.commands import CoordinatorGroup, state_embed

from tests.test_coordinator_discord import FakeBridge, an_interaction


def ids(view):
    return [item.item.custom_id for item in view.children]


async def test_the_four_m4_commands_send_their_arguments():
    notice = {"event": "coordinator_notice", "ok": True, "text": "ok"}
    bridge, record = FakeBridge(notice), []
    group = CoordinatorGroup(bridge)
    await group.planning.callback(group, an_interaction(record), "Server API; UI screens ;; Slides")
    await group.checkin.callback(group, an_interaction(record))
    await group.task.callback(group, an_interaction(record), 2, "done")
    await group.why.callback(group, an_interaction(record), "Why think-aloud?")
    assert bridge.sent == [
        ("planning", {"text": "Server API\nUI screens\nSlides"}),
        ("checkin", None),
        ("task", {"task": "2", "status": "done"}),
        ("why", {"question": "Why think-aloud?"}),
    ]


def test_the_plan_embed_numbers_tasks_for_the_task_command():
    embed = state_embed({"tasks": [{"title": "Server", "status": "doing", "owner_id": 7, "due_date": "2026-11-28"},
                                   {"title": "Slides", "status": "todo"}]})
    tasks = {f.name: f.value for f in embed.fields}["Tasks"]
    assert tasks == "• 1. Server · doing · <@7> · 2026-11-28\n• 2. Slides · todo"


PLAN = {"proposal_id": "b1", "kind": "plan", "status": "pending", "rationale": "r",
        "payload": {"items": [{"title": "Server", "owner_id": 7, "reason": "Python skills", "due_date": "2026-11-28"},
                              {"title": "Slides", "owner_id": None, "reason": "", "due_date": None}]}}
CHECKIN = {"proposal_id": "c2", "kind": "checkin", "status": "pending", "rationale": "r",
           "payload": {"findings": ["Late: Server"], "options": [{"label": "Move to 28 Nov", "task_id": "a"},
                                                                 {"label": "Bruno takes it", "task_id": "a"}]}}
BLOCKER = {"proposal_id": "e3", "kind": "blocker", "status": "pending", "rationale": "r",
           "payload": {"context": {"strategy_id": "cs7_blockers_dependencies", "topic": "UI", "evidence": []},
                       "title": "UI", "helper_id": 9, "question": "What do you need?"}}


def test_plan_card_lists_owners_and_reasons_and_is_confirmed_at_once():
    fields = {f.name: f.value for f in proposal_embed(PLAN).fields}
    assert fields["Tasks"] == "• **Server** — <@7> · 2026-11-28\n  _Python skills_\n• **Slides** — anyone"
    assert ids(card_view(PLAN)) == ["coord:confirm:b1", "coord:reject:b1"]


def test_checkin_card_shows_findings_and_one_button_per_option():
    fields = {f.name: f.value for f in proposal_embed(CHECKIN).fields}
    assert fields["What is late or at risk"] == "• Late: Server"
    assert ids(card_view(CHECKIN)) == ["coord:choose0:c2", "coord:choose1:c2", "coord:reject:c2"]


def test_blocker_card_is_proactive():
    embed = proposal_embed(BLOCKER)
    assert embed.title == "Coordinator · Something is blocked"
    assert {f.name: f.value for f in embed.fields}["Who could help"] == "<@9>"
    assert ids(card_view(BLOCKER)) == ["coord:confirm:e3", "coord:reject:e3", "coord:why:e3", "coord:helpful:e3", "coord:not_now:e3"]
