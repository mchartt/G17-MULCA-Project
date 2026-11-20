"""
The web adapter (mulca_discord/web/): store, HTTP API, WebSocket, and one
end-to-end run against a real local MUCA-Server with the coordinator on (the
model is a fake that always answers with a charter: no network, no cost).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3

import httpx
import pytest
import uvicorn
import websockets

from mulca_discord.sessions import SessionRegistry
from mulca_discord.web import WebHub, WebStore, create_web_app
from mulca_discord.web.store import INVITE_ALPHABET, INVITE_LENGTH, MEMBER_ID_MAX, MEMBER_ID_MIN, hash_token
from tests.test_coordinator_discord import coordinator_server  # noqa: F401  (pytest fixture)
from tests.test_muca_client import free_port

# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------


def test_a_group_gets_an_unambiguous_invite_code_and_its_own_conversation(tmp_path):
    store = WebStore(tmp_path / "w.db")
    group = store.create_group("Team 17")
    assert len(group.invite_code) == INVITE_LENGTH
    assert set(group.invite_code) <= set(INVITE_ALPHABET)
    assert group.conversation_id == f"web:{group.invite_code}"
    assert store.group_by_code(group.invite_code.lower()) == group


def test_tokens_are_stored_hashed_and_member_ids_never_look_like_discord_ids(tmp_path):
    path = tmp_path / "w.db"
    store = WebStore(path)
    group = store.create_group("Team")
    member, token = store.add_member(group.id, "Ada")
    assert MEMBER_ID_MIN <= member.id < MEMBER_ID_MAX
    assert store.member_by_token(token) == member
    assert store.member_by_token("not-a-token") is None
    raw = sqlite3.connect(path).execute("SELECT token_hash FROM web_member").fetchone()[0]
    assert raw == hash_token(token) and token not in raw


def test_history_is_in_order_capped_and_agent_messages_have_no_author(tmp_path):
    store = WebStore(tmp_path / "w.db")
    group = store.create_group("Team")
    ada, _ = store.add_member(group.id, "Ada")
    for i in range(5):
        store.add_message(group.id, ada.id, f"m{i}")
    reply = store.add_message(group.id, None, "Stepping in")
    store.update_message(reply.id, "Stepping in because…")
    history = store.history(group.id, limit=3)
    assert [m.text for m in history] == ["m3", "m4", "Stepping in because…"]
    assert history[-1].to_json({})["author"] is None
    assert history[0].to_json({ada.id: "Ada"})["author"] == {"id": ada.id, "name": "Ada"}


def test_deleting_a_group_deletes_its_members_and_messages(tmp_path):
    store = WebStore(tmp_path / "w.db")
    group = store.create_group("Team")
    ada, token = store.add_member(group.id, "Ada")
    store.add_message(group.id, ada.id, "hi")
    store.delete_group(group.id)
    assert store.member_by_token(token) is None
    assert store.history(group.id) == []


# ----------------------------------------------------------------------
# HTTP API (no MUCA-Server needed)
# ----------------------------------------------------------------------


@pytest.fixture
def hub(tmp_path):
    return WebHub(WebStore(tmp_path / "w.db"), "ws://127.0.0.1:9/")  # unreachable on purpose


async def _api(hub):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_web_app(hub)), base_url="http://t")


async def test_create_join_and_session(hub):
    async with await _api(hub) as api:
        created = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
        joined = await api.post("/api/join", json={"inviteCode": created["inviteCode"].lower(), "displayName": "Bruno"})
        assert joined.status_code == 200
        me = (await api.get("/api/session", headers={"Authorization": f"Bearer {joined.json()['token']}"})).json()
        assert me["me"]["name"] == "Bruno" and me["group"]["name"] == "Team 17"


async def test_a_wrong_code_or_token_is_refused(hub):
    async with await _api(hub) as api:
        assert (await api.post("/api/join", json={"inviteCode": "ZZZZZZZZZZ", "displayName": "Eve"})).status_code == 404
        assert (await api.get("/api/session", headers={"Authorization": "Bearer nope"})).status_code == 401
        assert (await api.post("/api/groups", json={"groupName": "", "displayName": "Eve"})).status_code == 422


# ----------------------------------------------------------------------
# WebSocket, against a real MUCA-Server (in process, fake model)
# ----------------------------------------------------------------------


@pytest.fixture
async def web(tmp_path, coordinator_server):  # noqa: F811
    hub = WebHub(WebStore(tmp_path / "w.db"), coordinator_server)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_web_app(hub), host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.01)
    yield hub, f"http://127.0.0.1:{port}", f"ws://127.0.0.1:{port}/ws"
    await hub.close()
    server.should_exit = True
    await task


class Tab:
    """One browser tab: a socket and everything it received."""

    def __init__(self, ws) -> None:
        self.ws = ws
        self.seen: list[dict] = []

    @classmethod
    async def open(cls, url: str, token: str) -> "Tab":
        tab = cls(await websockets.connect(url))
        await tab.ws.send(json.dumps({"type": "auth", "token": token}))
        tab.seen.append(json.loads(await tab.ws.recv()))
        return tab

    async def send(self, **frame) -> None:
        await self.ws.send(json.dumps(frame))

    async def wait_for(self, check, timeout: float = 20.0) -> dict:
        for item in self.seen:
            if check(item):
                return item
        async with asyncio.timeout(timeout):
            while True:
                item = json.loads(await self.ws.recv())
                self.seen.append(item)
                if check(item):
                    return item


async def test_a_socket_without_a_valid_token_is_closed(web):
    _, _, ws_url = web
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"type": "auth", "token": "nope"}))
        with pytest.raises(websockets.ConnectionClosed) as closed:
            await ws.recv()
        assert closed.value.rcvd.code == 4401


async def test_chat_kickoff_card_and_confirm_end_to_end(web):
    hub, http, ws_url = web
    async with httpx.AsyncClient(base_url=http) as api:
        ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
        bruno = (await api.post("/api/join", json={"inviteCode": ada["inviteCode"], "displayName": "Bruno"})).json()
        other = (await api.post("/api/groups", json={"groupName": "Other", "displayName": "Eve"})).json()

    tab_a, tab_b, tab_e = [await Tab.open(ws_url, t["token"]) for t in (ada, bruno, other)]
    assert tab_a.seen[0]["type"] == "hello" and [m["name"] for m in tab_b.seen[0]["members"]] == ["Ada", "Bruno"]

    # A message reaches the whole group, and the agent's reply arrives as a message with no author.
    await tab_a.send(type="message", text="@coordinator hello")
    mine = await tab_b.wait_for(lambda e: e["type"] == "message" and e["message"]["author"])
    assert mine["message"] == {**mine["message"], "text": "@coordinator hello", "channel": "web"}
    await tab_b.wait_for(lambda e: e["type"] == "message" and e["message"]["author"] is None)

    # Kickoff: the card reaches every tab of the group, the answer only the asker.
    await tab_b.send(type="command", command="kickoff", args={"text": "Deliver by 2 Dec."}, requestId="k1")
    reply = await tab_b.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "k1")
    assert reply["answer"]["ok"], reply
    card = await tab_a.wait_for(lambda e: e["type"] == "proposal")
    assert card["proposal"]["status"] == "pending"
    assert card["proposal"]["rationale"].startswith("Stepping in because")

    # The first valid click applies it; every tab sees the card change.
    await tab_a.send(type="click", proposalId=card["proposal"]["proposal_id"], action="confirm", requestId="c1")
    await tab_a.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "c1" and e["answer"]["ok"])
    await tab_b.wait_for(lambda e: e["type"] == "proposal" and e["proposal"]["status"] == "applied")

    # The panel: state with the confirmed charter, confirmed by Ada.
    await tab_b.send(type="command", command="state", requestId="s1")
    state = await tab_b.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "s1")
    assert state["answer"]["state"]["charter"]["goal"] == "Ship the coordinator."
    assert state["answer"]["state"]["charter"]["confirmed_by"] == ada["memberId"]

    # Another group's tab saw none of it.
    assert [e["type"] for e in tab_e.seen] == ["hello"]
    for tab in (tab_a, tab_b, tab_e):
        await tab.ws.close()


async def test_the_web_hook_does_not_touch_discords_class_hook(tmp_path):
    before = SessionRegistry.on_coordinator_event
    hub = WebHub(WebStore(tmp_path / "w.db"), "ws://127.0.0.1:9/")
    assert SessionRegistry.on_coordinator_event is before
    assert hub.registry.on_coordinator_event == hub._on_coordinator_event


async def test_with_muca_server_down_the_chat_still_works_and_says_so(hub):
    group, member, _ = hub.create_group("Team", "Ada")
    seen = []

    class Sock:
        async def send_json(self, data):
            seen.append(data)

    hub.registry._reconnect_delays = (0.0,)
    await hub.connect(Sock(), member)
    await hub.post_message(member, "anyone?")
    assert [e["type"] for e in seen] == ["hello", "message", "status"]
    assert seen[-1] == {"type": "status", "coordinator": "unavailable"}
    answer = await hub.command(member, "state")
    assert answer == {"type": "notice", "ok": False, "text": "The coordinator is not available right now. The chat still works; try the command again in a minute."}


# ----------------------------------------------------------------------
# Serving the built frontend and the film, invalid frames, the runner
# ----------------------------------------------------------------------


async def test_the_app_serves_the_frontend_routes_and_the_film(tmp_path, hub):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "assets" / "main.js").write_text("js")
    (dist / "favicon.svg").write_text("<svg/>")
    film = tmp_path / "film" / "desktop"
    film.mkdir(parents=True)
    (film / "f_0001.jpg").write_bytes(b"jpg")
    app = create_web_app(hub, static_dir=dist, film_dir=tmp_path / "film")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
        assert (await api.get("/")).text == "<html>app</html>"
        assert (await api.get("/space/console")).text == "<html>app</html>"  # client-side route
        assert (await api.get("/favicon.svg")).text == "<svg/>"
        assert (await api.get("/assets/main.js")).text == "js"
        assert (await api.get("/film/desktop/f_0001.jpg")).content == b"jpg"
        assert (await api.get("/..%2F..%2Fetc%2Fpasswd")).text == "<html>app</html>"


async def test_an_invalid_frame_gets_an_error_and_the_socket_stays_open(web):
    hub, http, ws_url = web
    async with httpx.AsyncClient(base_url=http) as api:
        ada = (await api.post("/api/groups", json={"groupName": "T", "displayName": "Ada"})).json()
    tab = await Tab.open(ws_url, ada["token"])
    await tab.send(type="command", command="rm -rf", requestId="x")
    error = await tab.wait_for(lambda e: e["type"] == "error")
    assert error["text"] == "That request was not understood."
    await tab.send(type="message", text="   ")  # blank: ignored, socket still fine
    await tab.send(type="message", text="still here")
    await tab.wait_for(lambda e: e["type"] == "message" and e["message"]["text"] == "still here")
    await tab.ws.close()


async def test_a_socket_that_never_authenticates_is_closed(web, monkeypatch):
    import mulca_discord.web.app as app_module

    monkeypatch.setattr(app_module, "AUTH_TIMEOUT_SECONDS", 0.2)
    _, _, ws_url = web
    async with websockets.connect(ws_url) as ws:
        with pytest.raises(websockets.ConnectionClosed) as closed:
            await ws.recv()
        assert closed.value.rcvd.code == 4401


def test_the_runner_builds_the_app_from_the_environment(tmp_path, monkeypatch):
    import mulca_discord.web.__main__ as runner

    served = []

    async def serve(self):
        served.append((self.config.host, self.config.port))

    monkeypatch.setattr(runner.uvicorn.Server, "serve", serve)
    monkeypatch.setenv("MULCA_WEB_DB", str(tmp_path / "data" / "w.db"))
    monkeypatch.setenv("MULCA_WEB_PORT", "8099")
    runner.main()
    assert served == [("127.0.0.1", 8099)]
    assert (tmp_path / "data" / "w.db").exists()


async def test_messages_reach_the_group_in_the_order_they_were_typed(web):
    hub, http, ws_url = web
    async with httpx.AsyncClient(base_url=http) as api:
        ada = (await api.post("/api/groups", json={"groupName": "T", "displayName": "Ada"})).json()
    tab = await Tab.open(ws_url, ada["token"])
    for i in range(5):
        await tab.send(type="message", text=f"m{i}")
    await tab.wait_for(lambda e: e["type"] == "message" and e["message"]["text"] == "m4")
    mine = [e["message"]["text"] for e in tab.seen if e["type"] == "message" and e["message"]["author"]]
    assert mine == ["m0", "m1", "m2", "m3", "m4"]
    await tab.ws.close()


async def test_health_and_cors_only_for_the_listed_origins(hub):
    app = create_web_app(hub, allowed_origins=["https://cadence.example"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as api:
        assert (await api.get("/api/health")).json() == {"ok": True}
        ok = await api.options("/api/groups", headers={"Origin": "https://cadence.example", "Access-Control-Request-Method": "POST"})
        assert ok.headers.get("access-control-allow-origin") == "https://cadence.example"
        no = await api.options("/api/groups", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
        assert no.headers.get("access-control-allow-origin") is None


async def test_a_broadcast_never_overtakes_a_new_members_hello(hub):
    """
    M3 e2e finding: "Bruno joined" written to Ada's socket before her hello
    would be overwritten by the older member list inside the hello.
    """
    group, ada, _ = hub.create_group("G", "Ada")
    order: list[str] = []
    gate = asyncio.Event()

    class SlowSocket:
        async def send_json(self, data):
            if data["type"] == "hello":
                await gate.wait()  # the hello is still being written...
            order.append(data["type"])

    connecting = asyncio.create_task(hub.connect(SlowSocket(), ada))
    await asyncio.sleep(0)
    joining = asyncio.create_task(hub.join_group(group.invite_code, "Bruno"))  # ...when Bruno joins
    await asyncio.sleep(0.05)
    gate.set()
    await asyncio.gather(connecting, joining)
    assert order == ["hello", "members"]


async def test_a_frame_that_does_not_validate_still_answers_its_request(hub):
    """M4 finding: an unknown command left the button waiting forever."""
    from mulca_discord.web.app import _handle

    sent = []

    class Ws:
        async def send_json(self, data):
            sent.append(data)

    group, ada, _ = hub.create_group("G", "Ada")
    await _handle(hub, Ws(), ada, {"type": "command", "command": "delete_everything", "requestId": "r9"})
    assert sent[0] == {"type": "reply", "requestId": "r9", "answer": {"type": "notice", "ok": False, "text": "That request was not understood."}}
    assert sent[1]["type"] == "error"


async def test_a_message_that_calls_cadence_is_answered_by_cadence_not_by_the_lab_agent(hub):
    """
    Matteo, 20/11: "@Cadence ...", "Cadence, ..." and "@coordinator ..." call
    Cadence, with or without a question mark: the coordinator answers from the
    project (command "ask", tests/test_web_limits.py); nothing is forwarded to
    the lab's agent, which cannot read the plan. Other messages reach
    MUCA-Server as before. The web chat keeps the member's own words.
    """
    group, member, _ = hub.create_group("Team", "Ada")
    sent, asked = [], []

    class Client:
        async def send_participants(self, roster, modality):
            pass

        async def send_user_text(self, **kw):
            sent.append(kw)

    async def run(group_id, action):
        await action(Client())

    async def command(member, name, args):
        asked.append((name, args))
        return {"type": "notice", "ok": True, "text": "Hello everyone!"}

    hub._run = run
    hub.command = command
    await hub.post_message(member, "@Cadence say hello to the group")
    await hub.post_message(member, "Cadence, ciao")
    # Right after Cadence answered: a message that does not name it reaches MUCA-Server
    # as usual and is also offered to Cadence as "maybe" (it may stay silent).
    await hub.post_message(member, "no mention here")
    await asyncio.sleep(0.05)
    assert asked == [
        ("ask", {"question": "say hello to the group"}),
        ("ask", {"question": "ciao"}),
        ("ask", {"question": "no mention here", "maybe": True}),
    ]
    assert [(s["text"], s["mentions_assistant"]) for s in sent] == [("no mention here", False)]
    members_said = [m.text for m in hub.store.history(group.id) if m.text != "Hello everyone!"]
    assert members_said == ["@Cadence say hello to the group", "Cadence, ciao", "no mention here"]
