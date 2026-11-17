"""
The web adapter lets two more coordinator commands through: "language" (the
language of Cadence's texts for the group) and "charter" (a member edits the
goal: a card, saved only when confirmed). Real local MUCA-Server, fake model.
"""

from __future__ import annotations

import httpx

from tests.test_web import Tab
from tests.test_web_limits import stack  # noqa: F401  (pytest fixture)


async def open_space(http: str, ws_url: str) -> Tab:
    async with httpx.AsyncClient(base_url=http) as api:
        ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
    return await Tab.open(ws_url, ada["token"])


async def test_the_group_chooses_the_language_and_every_tab_gets_it_with_the_state(stack):  # noqa: F811
    _, _, http, ws_url = stack
    tab = await open_space(http, ws_url)
    await tab.send(type="command", command="language", args={"language": "it"}, requestId="l1")
    reply = await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "l1")
    assert reply["answer"] == {"type": "notice", "ok": True, "text": "Cadence now writes in Italian."}
    state = await tab.wait_for(lambda e: e["type"] == "state" and e["state"].get("language") == "it")
    assert state["state"]["charter"] is None
    await tab.ws.close()


async def test_an_edited_goal_arrives_as_a_card_and_is_saved_on_confirm(stack):  # noqa: F811
    _, _, http, ws_url = stack
    tab = await open_space(http, ws_url)
    await tab.send(type="command", command="charter", args={"goal": "Ship Cadence.", "deliverables": ["Report"]}, requestId="g1")
    card = await tab.wait_for(lambda e: e["type"] == "proposal")
    assert card["proposal"]["kind"] == "charter" and card["proposal"]["status"] == "pending"
    assert card["proposal"]["rationale"] == "Ada edited the goal and deliverables."

    await tab.send(type="click", proposalId=card["proposal"]["proposal_id"], action="confirm", requestId="c1")
    state = await tab.wait_for(lambda e: e["type"] == "state" and e["state"].get("charter"))
    assert state["state"]["charter"]["goal"] == "Ship Cadence."
    assert state["state"]["charter"]["deliverables"] == ["Report"]
    await tab.ws.close()
