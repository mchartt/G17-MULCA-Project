"""
Calendar feed (M5, spec N3): milestones and task deadlines of a group as a
read-only iCalendar (.ics) feed that each member subscribes to from Google
Calendar or Outlook. No external API: the calendar app downloads the file
from the web adapter now and then.

    POST /api/calendar           (member token)  -> a new feed link; the old one stops working
    GET  /api/calendar/<t>.ics   (no login)      -> the feed; <t> is the secret

Security (project rules, section 10): the feed token is random (32 bytes),
stored hashed, revocable (a new link replaces the old), and only opens the
feed of one group. The feed is built from the last project state the adapter
received from MUCA-Server (`save_state`, on every coordinator_state), so a
calendar app polling it costs no model call and no server round trip.
"""

from __future__ import annotations

import json
import secrets
import time
from datetime import date, datetime, timedelta, timezone

from .store import WebStore, hash_token

SCHEMA = """
CREATE TABLE IF NOT EXISTS web_calendar (
    group_id    INTEGER PRIMARY KEY REFERENCES web_group(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS web_state (
    group_id    INTEGER PRIMARY KEY REFERENCES web_group(id) ON DELETE CASCADE,
    state_json  TEXT NOT NULL,
    updated_at  REAL NOT NULL
);
"""


class CalendarFeeds:
    def __init__(self, store: WebStore) -> None:
        self._store = store
        self._db = store.connection
        self._db.executescript(SCHEMA)

    def new_link(self, group_id: int) -> str:
        """A new secret for the group's feed; the previous one stops working."""
        token = secrets.token_urlsafe(32)
        with self._db:
            self._db.execute(
                "INSERT INTO web_calendar (group_id, token_hash, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(group_id) DO UPDATE SET token_hash = excluded.token_hash, created_at = excluded.created_at",
                (group_id, hash_token(token), time.time()),
            )
        return token

    def group_for(self, token: str) -> int | None:
        row = self._db.execute("SELECT group_id FROM web_calendar WHERE token_hash = ?", (hash_token(token),)).fetchone()
        return row[0] if row else None

    def save_state(self, group_id: int, state: dict) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO web_state (group_id, state_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(group_id) DO UPDATE SET state_json = excluded.state_json, updated_at = excluded.updated_at",
                (group_id, json.dumps(state), time.time()),
            )

    def feed(self, token: str) -> str | None:
        """The .ics text for this secret, or None if it opens nothing."""
        group_id = self.group_for(token)
        if group_id is None:
            return None
        group = self._store.group(group_id)
        row = self._db.execute("SELECT state_json FROM web_state WHERE group_id = ?", (group_id,)).fetchone()
        state = json.loads(row[0]) if row else {}
        names = {m.id: m.display_name for m in self._store.members(group_id)}
        return ics(group.name, group.id, state, names)


def ics(group_name: str, group_id: int, state: dict, names: dict[int, str], now: datetime | None = None) -> str:
    """
    RFC 5545 text: one all-day event per milestone with a date and per task
    with a due date that is not done. Lines end with CRLF and are folded at
    75 characters, as the standard asks.
    """
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Group 17//Cadence Group Coordinator//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape('Cadence · ' + group_name)}",
    ]
    for m in state.get("milestones") or []:
        if m.get("due_date"):
            lines += _event(f"milestone-{m.get('milestone_id', m['title'])}-{group_id}", stamp, m["due_date"],
                            f"Milestone: {m['title']}", f"Project milestone of {group_name}.")
    for t in state.get("tasks") or []:
        if t.get("due_date") and t.get("status") != "done":
            owner = names.get(t.get("owner_id")) or _profile_name(state, t.get("owner_id")) or "no owner yet"
            lines += _event(f"task-{t.get('task_id', t['title'])}-{group_id}", stamp, t["due_date"],
                            f"Task: {t['title']} ({owner})", f"Status: {t.get('status', 'todo')}. Owner: {owner}.")
    lines.append("END:VCALENDAR")
    return "".join(_fold(line) + "\r\n" for line in lines)


def _event(uid: str, stamp: str, day: str, summary: str, description: str) -> list[str]:
    start = date.fromisoformat(day)
    return [
        "BEGIN:VEVENT",
        f"UID:{_escape(uid)}@cadence",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{start:%Y%m%d}",
        f"DTEND;VALUE=DATE:{start + timedelta(days=1):%Y%m%d}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]


def _profile_name(state: dict, member_id) -> str | None:
    return next((m.get("display_name") for m in state.get("members") or [] if m.get("member_id") == member_id), None)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Lines longer than 75 octets continue on the next line after a space."""
    data = line.encode()
    if len(data) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        encoded = char.encode()
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode())
            current = b""
        current += encoded
    parts.append(current.decode())
    return "\r\n ".join(parts)
