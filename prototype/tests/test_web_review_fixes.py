"""
From the team's review of the 17 Nov build, on the web adapter: a document's
text for the assignment, a cap on the members of a space, the background a
person writes about themselves, and tasks and milestones edited by hand.
Real local MUCA-Server, fake model, no network.
"""

from __future__ import annotations

import io

import httpx

from mulca_discord.web import WebHub, WebStore, create_web_app
from tests.test_web import Tab
from tests.test_web_limits import stack  # noqa: F401  (pytest fixture)


def api_for(hub: WebHub) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_web_app(hub)), base_url="http://t")


def docx_bytes(*paragraphs: str) -> bytes:
    import docx

    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def test_a_members_document_comes_back_as_text_and_is_not_kept(tmp_path):
    hub = WebHub(WebStore(tmp_path / "w.sqlite3"), "ws://127.0.0.1:9/")
    async with api_for(hub) as api:
        ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
        auth = {"Authorization": f"Bearer {ada['token']}"}
        word = await api.post("/api/extract", content=docx_bytes("Build a coordinator.", "Demo on 2 December."),
                              headers={**auth, "X-File-Name": "Assignment%20v2.docx"})
        assert word.status_code == 200
        assert word.json() == {"name": "Assignment v2.docx", "text": "Build a coordinator.\nDemo on 2 December.", "truncated": False}

        plain = await api.post("/api/extract", content=("x" * 25_000).encode(), headers={**auth, "X-File-Name": "notes.txt"})
        assert len(plain.json()["text"]) == 20_000 and plain.json()["truncated"] is True

        # Nobody outside a space can use the server to read files.
        assert (await api.post("/api/extract", content=b"hello", headers={"X-File-Name": "a.txt"})).status_code == 401
        # A picture, an empty file: said plainly.
        assert (await api.post("/api/extract", content=b"\x89PNG....", headers={**auth, "X-File-Name": "scan.png"})).status_code == 422
        assert (await api.post("/api/extract", content=b"   ", headers={**auth, "X-File-Name": "empty.txt"})).status_code == 422
        too_big = await api.post("/api/extract", content=b"x" * (10 * 1024 * 1024 + 1), headers={**auth, "X-File-Name": "big.txt"})
        assert too_big.status_code == 413
    assert list(tmp_path.iterdir()) == [tmp_path / "w.sqlite3"] or all(p.name.startswith("w.sqlite3") for p in tmp_path.iterdir())


async def test_a_space_stops_accepting_members_at_its_cap(tmp_path):
    hub = WebHub(WebStore(tmp_path / "w.sqlite3"), "ws://127.0.0.1:9/", max_members=3)
    async with api_for(hub) as api:
        ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
        for name in ("Bruno", "Chiara"):
            assert (await api.post("/api/join", json={"inviteCode": ada["inviteCode"], "displayName": name})).status_code == 200
        full = await api.post("/api/join", json={"inviteCode": ada["inviteCode"], "displayName": "Dario"})
        assert full.status_code == 409
        assert full.json()["detail"] == "This space is full: a group has at most 3 members."
        assert [m.display_name for m in hub.store.members(hub.store.group_by_code(ada["inviteCode"]).id)] == ["Ada", "Bruno", "Chiara"]


async def test_a_person_already_in_a_full_space_still_gets_back_in(tmp_path):
    hub = WebHub(WebStore(tmp_path / "w.sqlite3"), "ws://127.0.0.1:9/", max_members=1)
    async with api_for(hub) as api:
        session = (await api.post("/api/register", json={"email": "ada@example.org", "password": "correct horse", "displayName": "Ada"})).json()
        auth = {"Authorization": f"Bearer {session['accountToken']}"}
        space = (await api.post("/api/groups", json={"groupName": "Solo"}, headers=auth)).json()
        again = await api.post("/api/join", json={"inviteCode": space["inviteCode"]}, headers=auth)  # a second browser
        assert again.status_code == 200 and again.json()["memberId"] == space["memberId"]


async def test_the_background_is_part_of_the_account_and_of_what_the_coordinator_gets(tmp_path):
    hub = WebHub(WebStore(tmp_path / "w.sqlite3"), "ws://127.0.0.1:9/")
    async with api_for(hub) as api:
        session = (await api.post("/api/register", json={"email": "ada@example.org", "password": "correct horse", "displayName": "Ada"})).json()
        auth = {"Authorization": f"Bearer {session['accountToken']}"}
        saved = await api.put("/api/me", headers=auth, json={
            "displayName": "Ada", "discipline": "Design", "skills": ["Figma"], "weeklyHours": 6,
            "background": "  Two years of user research at a museum.  ",
        })
        assert saved.json()["user"]["background"] == "Two years of user research at a museum."
        assert (await api.get("/api/me", headers=auth)).json()["user"]["background"].startswith("Two years")
        too_long = await api.put("/api/me", headers=auth, json={"displayName": "Ada", "background": "x" * 601})
        assert too_long.status_code == 422
    assert hub.accounts.user(session["user"]["id"]).profile_args()["background"] == "Two years of user research at a museum."


async def test_tasks_and_milestones_are_edited_by_hand_over_the_socket(stack):  # noqa: F811
    _, _, http, ws_url = stack
    async with httpx.AsyncClient(base_url=http) as api:
        ada = (await api.post("/api/groups", json={"groupName": "Team 17", "displayName": "Ada"})).json()
    tab = await Tab.open(ws_url, ada["token"])

    await tab.send(type="command", command="task", args={"add": "Write the report", "owner": ada["memberId"]}, requestId="t1")
    reply = await tab.wait_for(lambda e: e["type"] == "reply" and e["requestId"] == "t1")
    assert reply["answer"]["text"] == "Task added: “Write the report” (Ada)."
    state = await tab.wait_for(lambda e: e["type"] == "state" and e["state"]["tasks"])
    task = state["state"]["tasks"][0]
    assert task["owner_id"] == ada["memberId"] and task["status"] == "todo"

    await tab.send(type="command", command="task", args={"task": task["task_id"], "status": "done", "owner": ""}, requestId="t2")
    done = await tab.wait_for(lambda e: e["type"] == "state" and e["state"]["tasks"] and e["state"]["tasks"][0]["status"] == "done")
    assert done["state"]["tasks"][0]["owner_id"] is None

    await tab.send(type="command", command="milestone", args={"add": "Demo", "due": "2026-12-02"}, requestId="m1")
    with_milestone = await tab.wait_for(lambda e: e["type"] == "state" and e["state"]["milestones"])
    assert (with_milestone["state"]["milestones"][0]["title"], with_milestone["state"]["milestones"][0]["due_date"]) == ("Demo", "2026-12-02")
    assert with_milestone["state"]["milestones"][0]["milestone_id"]
    await tab.ws.close()
