"""
Known limits closed after M5, on the web side: "Helpful" clicks pass
through, "@coordinator why ..." typed in the chat is answered from the
decision log (not by the lab's agent), and "Delete space" removes the
group's data on MUCA-Server and then on the web side. Real local
MUCA-Server, fake model, no network.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
import uvicorn
from muca_server import create_app
from muca_server.cognition.coordination.settings import CoordinatorSettings
from muca_server.cognition.coordination.wiring import build_coordinator_factory
from muca_server.cognition.memory.sqlite import db_path_for
from muca_server.sessions import DefaultSessionComponentsFactory

from mulca_discord.web import WebHub, WebStore, create_web_app
from mulca_discord.web.hub import TYPED_WHY
from mulca_discord.web.server_data import delete_conversation, http_base
from tests.test_coordinator_discord import AnswerEverything, Factory, FakeChat
from tests.test_muca_client import free_port
from tests.test_web import Tab

TOKEN = "admin-token-for-tests"


@pytest.fixture
async def stack(tmp_path):
    """MUCA-Server (coordinator on, admin token) + web adapter, both local."""
    db_dir = tmp_path / "muca"
    db_dir.mkdir()
    muca = create_app(
        components_factory=DefaultSessionComponentsFactory(
            agent_factory=Factory(),
            policy_factory=lambda context: AnswerEverything(),
            coordinator_factory=build_coordinator_factory(
                CoordinatorSettings(enabled=True), client=FakeChat(), db_dir=str(db_dir)
            ),
        ),
        db_dir=db_dir,
        admin_token=TOKEN,
    )
    servers = []

    async def serve(app):
        port = free_port()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        servers.append((server, asyncio.create_task(server.serve())))
        while not server.started:
            await asyncio.sleep(0.01)
        return port

    muca_port = await serve(muca)
    hub = WebHub(WebStore(tmp_path / "w.sqlite3"), f"ws://127.0.0.1:{muca_port}/", admin_token=TOKEN)
    web_port = await serve(create_web_app(hub))
    yield hub, db_dir, f"http://127.0.0.1:{web_port}", f"ws://127.0.0.1:{web_port}/ws"
    await hub.close()
    for server, task in servers:
        server.should_exit = True
        await task


def test_typed_why_matches_only_a_question_to_the_coordinator():
    assert TYPED_WHY.match("@coordinator why did we drop X?")["question"] == "why did we drop X?"
    assert TYPED_WHY.match("@Coordinator, perché abbiamo scelto SUS?")["question"].startswith("perché")
    assert TYPED_WHY.match("@coordinator: Perche Figma?")
    assert TYPED_WHY.match("@coordinator hello") is None
    assert TYPED_WHY.match("why @coordinator") is None
    assert TYPED_WHY.match("@coordinatorwhy") is None


def test_http_base_from_the_websocket_url():
    assert http_base("ws://localhost:8000/") == "http://localhost:8000"
    assert http_base("wss://muca.example.org/") == "https://muca.example.org"


async def test_without_an_admin_token_nothing_is_deleted_anywhere():
    assert await delete_conversation("ws://127.0.0.1:9/", "", "web:X") is False
    assert await delete_conversation("ws://127.0.0.1:9/", "t", "web:X") is False  # unreachable


async def test_typed_why_is_answered_from_the_log_in_the_chat(stack):
    hub, _, http, ws_url = stack
    async with httpx.AsyncClient(base_url=http) as api:
        ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
    tab = await Tab.open(ws_url, ada["token"])
    await tab.send(type="message", text="@coordinator why did we pick SUS?")
    answer = await tab.wait_for(lambda e: e["type"] == "message" and e["message"]["author"] is None)
    # Empty log: the server says so without a model call, and the lab's agent never answered.
    assert answer["message"]["text"] == "No decision has been recorded yet."
    await asyncio.sleep(0.3)
    agent_messages = [e for e in tab.seen if e["type"] == "message" and e["message"]["author"] is None]
    assert len(agent_messages) == 1
    await tab.ws.close()


async def test_helpful_click_passes_through_and_is_answered(stack):
    hub, _, http, ws_url = stack
    async with httpx.AsyncClient(base_url=http) as api:
        ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
    tab = await Tab.open(ws_url, ada["token"])
    await tab.send(type="click", proposalId="abc123", action="helpful", requestId="h1")
    reply = await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "h1")
    assert reply["answer"] == {"type": "notice", "ok": False, "text": "That card is not in this group."}
    await tab.ws.close()


async def test_delete_space_removes_server_and_web_data_after_typing_the_name(stack):
    hub, db_dir, http, ws_url = stack
    async with httpx.AsyncClient(base_url=http) as api:
        ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
        bruno = (await api.post("/api/join", json={"inviteCode": ada["inviteCode"], "displayName": "Bruno"})).json()
        tab = await Tab.open(ws_url, bruno["token"])
        await tab.send(type="command", command="profile", args={"discipline": "Design"}, requestId="p1")
        await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "p1")
        db_file = db_path_for(f"web:{ada['inviteCode']}", base_dir=db_dir)
        assert db_file.is_file()

        auth = {"Authorization": f"Bearer {ada['token']}"}
        assert (await api.post("/api/groups/delete", json={"confirm": "Team 18"}, headers=auth)).status_code == 400
        assert (await api.post("/api/groups/delete", json={"confirm": "Team 17"})).status_code == 401
        done = await api.post("/api/groups/delete", json={"confirm": " team  17 "}, headers=auth)
        assert done.status_code == 200 and done.json() == {"deleted": True}

        await tab.wait_for(lambda e: e["type"] == "deleted")
        assert not db_file.exists()
        assert hub.store.group_by_code(ada["inviteCode"]) is None
        assert (await api.get("/api/session", headers=auth)).status_code == 401


async def test_delete_space_keeps_everything_when_the_server_part_fails(tmp_path):
    hub = WebHub(WebStore(tmp_path / "w.sqlite3"), "ws://127.0.0.1:9/")  # no token, no server
    api = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_web_app(hub)), base_url="http://t")
    async with api:
        ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
        failed = await api.post("/api/groups/delete", json={"confirm": "Team 17"}, headers={"Authorization": f"Bearer {ada['token']}"})
        assert failed.status_code == 502
        assert hub.store.group_by_code(ada["inviteCode"]) is not None
