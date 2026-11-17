"""
WebStore: the web app's own small SQLite file -- groups, members, messages.

Only what the web channel needs: the project state (charter, plan, decisions)
lives in MUCA-Server, never here. Per member we keep only the display name and
a hash of the access token (project rule, section 10: name, discipline, skills,
hours and channel ids; discipline, skills and hours go to MUCA-Server through
the `profile` command).

One writer: the WebHub, in the MULCA process's event loop. The calls are short
and synchronous (sqlite3 from the standard library), which keeps the store easy
to explain and to test.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

# Invite codes: 10 characters without look-alikes (0/O, 1/I/l), so a code read
# aloud or copied from a slide still works. 31^10 ~ 8e14 possibilities.
INVITE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
INVITE_LENGTH = 10

# Participant ids for web members. Discord ids are snowflakes (> 1e17), so ids
# in [1e8, 1e9) can never collide with a Discord member in a shared roster.
MEMBER_ID_MIN = 100_000_000
MEMBER_ID_MAX = 999_999_999

# Messages kept per group for the chat history shown on (re)connect.
HISTORY_LIMIT = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS web_group (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    invite_code TEXT NOT NULL UNIQUE,
    conversation_id TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS web_member (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES web_group(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    joined_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS web_message (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL REFERENCES web_group(id) ON DELETE CASCADE,
    member_id INTEGER,          -- NULL: written by the coordinator, or mirrored
    channel TEXT NOT NULL,      -- 'web', or 'discord' / 'slack' for a mirrored message
    author_name TEXT,           -- only for a mirrored message: who wrote it there
    text TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class Group:
    id: int
    name: str
    invite_code: str
    conversation_id: str


@dataclass(frozen=True, slots=True)
class Member:
    id: int
    group_id: int
    display_name: str


@dataclass(frozen=True, slots=True)
class Message:
    id: int
    group_id: int
    member_id: int | None
    channel: str
    text: str
    created_at: float
    # A message mirrored from Discord or Slack: its author is not a web member.
    author_name: str | None = None

    def to_json(self, names: dict[int, str]) -> dict:
        if self.author_name is not None:
            author = {"id": 0, "name": self.author_name}
        elif self.member_id is None:
            author = None  # the coordinator
        else:
            author = {"id": self.member_id, "name": names.get(self.member_id, "Former member")}
        return {
            "id": self.id,
            "author": author,
            "channel": self.channel,
            "text": self.text,
            "ts": self.created_at,
        }


def hash_token(token: str) -> str:
    """Tokens are stored hashed: a leaked database file opens no group."""
    return hashlib.sha256(token.encode()).hexdigest()


class WebStore:
    def __init__(self, path: str | Path) -> None:
        self._db = sqlite3.connect(str(path))
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.executescript(SCHEMA)
        # Databases made before mirrored messages existed.
        if "author_name" not in {row[1] for row in self._db.execute("PRAGMA table_info(web_message)")}:
            self._db.execute("ALTER TABLE web_message ADD COLUMN author_name TEXT")

    def close(self) -> None:
        self._db.close()

    @property
    def connection(self) -> sqlite3.Connection:
        """The open database, shared with calendar.py (same file, same thread)."""
        return self._db

    # -- groups ---------------------------------------------------------

    def create_group(self, name: str) -> Group:
        code = self._unused(lambda: "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH)),
                            "SELECT 1 FROM web_group WHERE invite_code = ?")
        with self._db:
            cur = self._db.execute(
                "INSERT INTO web_group (name, invite_code, conversation_id, created_at) VALUES (?, ?, ?, ?)",
                (name, code, f"web:{code}", time.time()),
            )
        return self.group(cur.lastrowid)

    def group(self, group_id: int) -> Group | None:
        row = self._db.execute("SELECT * FROM web_group WHERE id = ?", (group_id,)).fetchone()
        return _group(row)

    def group_by_code(self, code: str) -> Group | None:
        row = self._db.execute(
            "SELECT * FROM web_group WHERE invite_code = ?", (code.strip().upper(),)
        ).fetchone()
        return _group(row)

    # -- members --------------------------------------------------------

    def add_member(self, group_id: int, display_name: str) -> tuple[Member, str]:
        """A new member and their access token (shown once, stored hashed)."""
        member_id = self._unused(
            lambda: MEMBER_ID_MIN + secrets.randbelow(MEMBER_ID_MAX - MEMBER_ID_MIN),
            "SELECT 1 FROM web_member WHERE id = ?",
        )
        token = secrets.token_urlsafe(32)
        with self._db:
            self._db.execute(
                "INSERT INTO web_member (id, group_id, display_name, token_hash, joined_at) VALUES (?, ?, ?, ?, ?)",
                (member_id, group_id, display_name, hash_token(token), time.time()),
            )
        return Member(member_id, group_id, display_name), token

    def member_by_token(self, token: str) -> Member | None:
        hashed = hash_token(token)
        row = self._db.execute(
            "SELECT id, group_id, display_name FROM web_member WHERE token_hash = ?", (hashed,)
        ).fetchone()
        if row is None and self._has_table("web_access"):
            # A token made for a logged-in person's other browser (accounts.py).
            row = self._db.execute(
                "SELECT m.id, m.group_id, m.display_name FROM web_access a "
                "JOIN web_member m ON m.id = a.member_id WHERE a.token_hash = ?",
                (hashed,),
            ).fetchone()
        return Member(row["id"], row["group_id"], row["display_name"]) if row else None

    def member(self, member_id: int) -> Member | None:
        row = self._db.execute(
            "SELECT id, group_id, display_name FROM web_member WHERE id = ?", (member_id,)
        ).fetchone()
        return Member(row["id"], row["group_id"], row["display_name"]) if row else None

    def _has_table(self, name: str) -> bool:
        return self._db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone() is not None

    def members(self, group_id: int) -> list[Member]:
        rows = self._db.execute(
            "SELECT id, group_id, display_name FROM web_member WHERE group_id = ? ORDER BY joined_at",
            (group_id,),
        ).fetchall()
        return [Member(r["id"], r["group_id"], r["display_name"]) for r in rows]

    # -- messages -------------------------------------------------------

    def add_message(
        self,
        group_id: int,
        member_id: int | None,
        text: str,
        channel: str = "web",
        *,
        author_name: str | None = None,
        at: float | None = None,
    ) -> Message:
        now = at or time.time()
        with self._db:
            cur = self._db.execute(
                "INSERT INTO web_message (group_id, member_id, channel, text, created_at, author_name) VALUES (?, ?, ?, ?, ?, ?)",
                (group_id, member_id, channel, text, now, author_name),
            )
        return Message(cur.lastrowid, group_id, member_id, channel, text, now, author_name)

    def update_message(self, message_id: int, text: str) -> Message:
        """A streamed agent reply grows: same row, longer text."""
        with self._db:
            self._db.execute("UPDATE web_message SET text = ? WHERE id = ?", (text, message_id))
        r = self._db.execute("SELECT * FROM web_message WHERE id = ?", (message_id,)).fetchone()
        return _message(r)

    def history(self, group_id: int, limit: int = HISTORY_LIMIT) -> list[Message]:
        rows = self._db.execute(
            "SELECT * FROM web_message WHERE group_id = ? ORDER BY id DESC LIMIT ?", (group_id, limit)
        ).fetchall()
        return [_message(r) for r in reversed(rows)]

    def delete_group(self, group_id: int) -> None:
        """Every web-side row of the group (members and messages cascade)."""
        with self._db:
            self._db.execute("DELETE FROM web_group WHERE id = ?", (group_id,))

    # -- helpers --------------------------------------------------------

    def _unused(self, make, query: str):
        while True:
            value = make()
            if self._db.execute(query, (value,)).fetchone() is None:
                return value


def _group(row) -> Group | None:
    if row is None:
        return None
    return Group(row["id"], row["name"], row["invite_code"], row["conversation_id"])


def _message(r) -> Message:
    return Message(r["id"], r["group_id"], r["member_id"], r["channel"], r["text"], r["created_at"], r["author_name"])
