"""M5: the calendar feed (.ics) of a web group: link, revocation, content, format."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from mulca_discord.web import WebHub, WebStore, create_web_app
from mulca_discord.web.calendar import ics

STATE = {
    "milestones": [{"milestone_id": "m1", "title": "Demo Madness", "due_date": "2026-12-02"},
                   {"milestone_id": "m2", "title": "No date yet", "due_date": None}],
    "tasks": [
        {"task_id": "t1", "title": "Server, API; tests", "owner_id": 5, "due_date": "2026-11-28", "status": "doing"},
        {"task_id": "t2", "title": "Done already", "owner_id": 5, "due_date": "2026-11-20", "status": "done"},
        {"task_id": "t3", "title": "Slides", "owner_id": None, "due_date": "2026-11-30", "status": "todo"},
    ],
}
NOW = datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc)


def test_the_feed_has_one_all_day_event_per_dated_milestone_and_open_task():
    text = ics("AUI group 17", 1, STATE, {5: "Ada"}, now=NOW)
    assert text.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and text.endswith("END:VCALENDAR\r\n")
    assert text.count("BEGIN:VEVENT") == 3  # Demo Madness, Server, Slides
    assert "DTSTART;VALUE=DATE:20261202\r\nDTEND;VALUE=DATE:20261203" in text
    assert "SUMMARY:Task: Server\\, API\\; tests (Ada)" in text  # RFC 5545 escaping
    assert "SUMMARY:Task: Slides (no owner yet)" in text
    assert "Done already" not in text and "No date yet" not in text
    assert "DTSTAMP:20261120T090000Z" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))


def test_long_lines_are_folded():
    state = {"milestones": [{"milestone_id": "m", "title": "x" * 200, "due_date": "2026-12-02"}]}
    text = ics("G", 1, state, {}, now=NOW)
    assert "\r\n x" in text
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))


async def test_a_member_gets_a_private_link_and_a_new_link_revokes_the_old(tmp_path):
    hub = WebHub(WebStore(tmp_path / "w.db"), "ws://127.0.0.1:9/")
    group, ada, token = hub.create_group("AUI group 17", "Ada")
    hub.calendar.save_state(group.id, STATE)
    app = create_web_app(hub)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.post("/api/calendar")).status_code == 401
        first = (await client.post("/api/calendar", headers={"Authorization": f"Bearer {token}"})).json()["path"]
        feed = await client.get(first)
        assert feed.status_code == 200 and feed.headers["content-type"].startswith("text/calendar")
        assert "Milestone: Demo Madness" in feed.text and "(Ada)" not in feed.text  # owner 5 is not a web member here
        second = (await client.post("/api/calendar", headers={"Authorization": f"Bearer {token}"})).json()["path"]
        assert second != first
        assert (await client.get(first)).status_code == 404
        assert (await client.get(second)).status_code == 200
        assert (await client.get("/api/calendar/guess.ics")).status_code == 404


async def test_the_feed_follows_the_state_the_server_sends(tmp_path):
    hub = WebHub(WebStore(tmp_path / "w.db"), "ws://127.0.0.1:9/")
    group, _, _ = hub.create_group("G", "Ada")
    token = hub.calendar.new_link(group.id)
    assert "BEGIN:VEVENT" not in hub.calendar.feed(token)  # no state yet: an empty calendar, not an error

    class Session:
        scope = type("S", (), {"conversation_id": group.conversation_id})()

    await hub._on_coordinator_event(Session(), {"event": "coordinator_state", "state": STATE})
    assert hub.calendar.feed(token).count("BEGIN:VEVENT") == 3


def test_my_file_has_the_milestones_and_only_my_tasks():
    text = ics("AUI group 17", 1, STATE, {5: "Ada"}, now=NOW, owner=5)
    assert "Milestone: Demo Madness" in text
    assert "Task: Server\, API\; tests (Ada)" in text
    assert "Slides" not in text  # nobody's task: not in Ada's file


async def test_add_to_my_calendar_downloads_a_file_for_the_member(tmp_path):
    """Matteo, 20/11: a file to import in Outlook or Google Calendar, nothing to keep secret."""
    hub = WebHub(WebStore(tmp_path / "w.db"), "ws://127.0.0.1:9/")
    group, ada, token = hub.create_group("AUI group 17", "Ada")
    state = {**STATE, "tasks": [{**t, "owner_id": ada.id if t["task_id"] == "t1" else t["owner_id"]} for t in STATE["tasks"]]}
    hub.calendar.save_state(group.id, state)
    app = create_web_app(hub)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        assert (await client.post("/api/calendar/file")).status_code == 401
        got = await client.post("/api/calendar/file", headers={"Authorization": f"Bearer {token}"})
    assert got.status_code == 200 and got.headers["content-type"].startswith("text/calendar")
    assert got.headers["content-disposition"] == 'attachment; filename="cadence.ics"'
    assert "Milestone: Demo Madness" in got.text and "Server" in got.text and "Slides" not in got.text
