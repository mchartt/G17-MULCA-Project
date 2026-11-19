"""
Renaming a space (Project settings, 19/11): a member's own action, no card.
The name is checked like a new space's (1-80 characters, spaces collapsed),
only a member's token may do it, and every open tab of the group hears it.
"""

from __future__ import annotations

import httpx
import pytest

from mulca_discord.web import WebHub, WebStore, create_web_app


class Tab:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, data) -> None:
        self.frames.append(data)


@pytest.fixture
def hub(tmp_path):
    return WebHub(WebStore(tmp_path / "w.db"), "ws://127.0.0.1:9/")  # unreachable on purpose


async def test_a_member_renames_the_space_and_every_tab_hears_it(hub):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_web_app(hub)), base_url="http://t") as api:
        created = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
        token = created["token"]
        member = hub.store.member_by_token(token)
        tab = Tab()
        hub._sockets.setdefault(member.group_id, set()).add(tab)  # noqa: SLF001 - an open tab of the group

        renamed = await api.post("/api/groups/rename", json={"name": "  AUI   group 17  "}, headers={"Authorization": f"Bearer {token}"})
        assert renamed.status_code == 200
        assert renamed.json()["group"]["name"] == "AUI group 17"
        assert hub.store.group(member.group_id).name == "AUI group 17"
        assert tab.frames == [{"type": "group", "group": {"id": member.group_id, "name": "AUI group 17", "inviteCode": created["inviteCode"]}}]

        session = (await api.get("/api/session", headers={"Authorization": f"Bearer {token}"})).json()
        assert session["group"]["name"] == "AUI group 17"


async def test_rename_needs_a_member_and_a_real_name(hub):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_web_app(hub)), base_url="http://t") as api:
        token = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()["token"]
        auth = {"Authorization": f"Bearer {token}"}
        assert (await api.post("/api/groups/rename", json={"name": "New"}, headers={"Authorization": "Bearer nope"})).status_code == 401
        assert (await api.post("/api/groups/rename", json={"name": "   "}, headers=auth)).status_code == 422
        assert (await api.post("/api/groups/rename", json={"name": "x" * 81}, headers=auth)).status_code == 422
