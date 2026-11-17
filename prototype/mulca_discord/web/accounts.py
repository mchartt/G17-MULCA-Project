"""
Accounts: register, log in, and a personal profile that follows the member
into every space they create or join.

Before this file a member was only "a name and a token in one browser". Now:

    web_user    one row per person: email, password (hashed), profile
    web_login   the browsers where that person is logged in (tokens, hashed)
    web_member  gains user_id: "this member of this space is that person"
    web_access  extra access tokens of a member, so the same person can open
                the same space from a second browser

What is kept is only what the project rules allow: email (to log in), display
name, discipline, skills, weekly hours. No scores, no activity statistics.

Passwords are never stored: only a salted scrypt hash (hashlib, standard
library). Tokens are stored hashed too (store.hash_token), so a leaked
database file opens no account.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass, field

from .store import hash_token

SCHEMA = """
CREATE TABLE IF NOT EXISTS web_user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,      -- lower case
    password_hash TEXT NOT NULL,             -- "scrypt$<salt hex>$<hash hex>"
    display_name  TEXT NOT NULL,
    discipline    TEXT NOT NULL DEFAULT '',
    skills_json   TEXT NOT NULL DEFAULT '[]',
    weekly_hours  INTEGER,
    created_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS web_login (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES web_user(id) ON DELETE CASCADE,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS web_access (
    token_hash TEXT PRIMARY KEY,
    member_id  INTEGER NOT NULL REFERENCES web_member(id) ON DELETE CASCADE,
    created_at REAL NOT NULL
);
"""

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
# A login lasts 30 days, then the person logs in again.
LOGIN_SECONDS = 30 * 24 * 3600
# After 5 wrong passwords, that email waits 5 minutes (slows down guessing).
MAX_FAILURES = 5
LOCK_SECONDS = 5 * 60


class AccountError(ValueError):
    """Something the person can fix; the message is shown in the form."""


@dataclass(frozen=True, slots=True)
class User:
    id: int
    email: str
    display_name: str
    discipline: str = ""
    skills: list[str] = field(default_factory=list)
    weekly_hours: int | None = None

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "displayName": self.display_name,
            "discipline": self.discipline,
            "skills": self.skills,
            "weeklyHours": self.weekly_hours,
        }

    def profile_args(self) -> dict:
        """The arguments of the coordinator's "profile" command."""
        return {
            "display_name": self.display_name,
            "discipline": self.discipline,
            "skills": self.skills,
            "weekly_hours": self.weekly_hours,
        }


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        _, salt_hex, _ = stored.split("$")
    except ValueError:
        return False
    # compare_digest: the time taken says nothing about where they differ.
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt_hex)), stored)


class Accounts:
    def __init__(self, db: sqlite3.Connection, *, clock=time.time) -> None:
        self._db = db
        self._clock = clock
        self._db.executescript(SCHEMA)
        # Older databases: members had no user. NULL = a guest member.
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(web_member)")}
        if "user_id" not in columns:
            self._db.execute("ALTER TABLE web_member ADD COLUMN user_id INTEGER REFERENCES web_user(id) ON DELETE SET NULL")
        # email -> (wrong passwords in a row, time of the last one); memory only.
        self._failures: dict[str, tuple[int, float]] = {}

    # -- register and log in ------------------------------------------------

    def register(self, email: str, password: str, display_name: str) -> tuple[User, str]:
        email = email.strip().lower()
        display_name = " ".join(display_name.split())[:40]
        if not EMAIL.match(email) or len(email) > 254:
            raise AccountError("Write a valid email address.")
        if len(password) < MIN_PASSWORD:
            raise AccountError(f"The password needs at least {MIN_PASSWORD} characters.")
        if not display_name:
            raise AccountError("Write the name your group will see.")
        try:
            with self._db:
                cur = self._db.execute(
                    "INSERT INTO web_user (email, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)",
                    (email, hash_password(password), display_name, self._clock()),
                )
        except sqlite3.IntegrityError:
            raise AccountError("An account with this email already exists. Log in instead.") from None
        return self.user(cur.lastrowid), self._new_login(cur.lastrowid)

    def login(self, email: str, password: str) -> tuple[User, str]:
        email = email.strip().lower()
        count, last = self._failures.get(email, (0, 0.0))
        if count >= MAX_FAILURES and self._clock() - last < LOCK_SECONDS:
            raise AccountError("Too many wrong passwords. Wait five minutes, then try again.")
        row = self._db.execute("SELECT id, password_hash FROM web_user WHERE email = ?", (email,)).fetchone()
        # The same answer for "no such email" and "wrong password": nobody can
        # find out which emails have an account.
        if row is None or not password_matches(password, row["password_hash"]):
            self._failures[email] = (count + 1 if self._clock() - last < LOCK_SECONDS else 1, self._clock())
            raise AccountError("Email or password not correct.")
        self._failures.pop(email, None)
        return self.user(row["id"]), self._new_login(row["id"])

    def logout(self, token: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM web_login WHERE token_hash = ?", (hash_token(token),))

    def user_by_token(self, token: str) -> User | None:
        row = self._db.execute(
            "SELECT user_id, created_at FROM web_login WHERE token_hash = ?", (hash_token(token),)
        ).fetchone()
        if row is None or self._clock() - row["created_at"] > LOGIN_SECONDS:
            return None
        return self.user(row["user_id"])

    def _new_login(self, user_id: int) -> str:
        token = secrets.token_urlsafe(32)
        with self._db:
            self._db.execute(
                "INSERT INTO web_login (token_hash, user_id, created_at) VALUES (?, ?, ?)",
                (hash_token(token), user_id, self._clock()),
            )
        return token

    # -- profile ------------------------------------------------------------

    def user(self, user_id: int) -> User | None:
        r = self._db.execute("SELECT * FROM web_user WHERE id = ?", (user_id,)).fetchone()
        if r is None:
            return None
        return User(r["id"], r["email"], r["display_name"], r["discipline"], json.loads(r["skills_json"]), r["weekly_hours"])

    def update_profile(
        self,
        user_id: int,
        *,
        display_name: str,
        discipline: str = "",
        skills: list[str] | None = None,
        weekly_hours: int | None = None,
    ) -> User:
        display_name = " ".join(display_name.split())[:40]
        if not display_name:
            raise AccountError("Write the name your group will see.")
        clean_skills = [s.strip()[:40] for s in (skills or []) if s.strip()][:20]
        with self._db:
            self._db.execute(
                "UPDATE web_user SET display_name = ?, discipline = ?, skills_json = ?, weekly_hours = ? WHERE id = ?",
                (display_name, discipline.strip()[:100], json.dumps(clean_skills), weekly_hours, user_id),
            )
            # The new name shows in every space of this person.
            self._db.execute("UPDATE web_member SET display_name = ? WHERE user_id = ?", (display_name, user_id))
        return self.user(user_id)

    def delete_user(self, user_id: int) -> None:
        """The account and its logins; the person's members stay as guests of their spaces."""
        with self._db:
            self._db.execute("DELETE FROM web_user WHERE id = ?", (user_id,))

    # -- the person's spaces ------------------------------------------------

    def claim_member(self, member_id: int, user_id: int) -> None:
        """This member of a space is that person."""
        with self._db:
            self._db.execute("UPDATE web_member SET user_id = ? WHERE id = ?", (user_id, member_id))

    def member_in(self, user_id: int, group_id: int) -> int | None:
        row = self._db.execute(
            "SELECT id FROM web_member WHERE user_id = ? AND group_id = ?", (user_id, group_id)
        ).fetchone()
        return row["id"] if row else None

    def member_ids(self, user_id: int) -> list[tuple[int, int]]:
        """(member id, group id) for every space of this person."""
        rows = self._db.execute("SELECT id, group_id FROM web_member WHERE user_id = ?", (user_id,)).fetchall()
        return [(r["id"], r["group_id"]) for r in rows]

    def spaces(self, user_id: int) -> list[dict]:
        rows = self._db.execute(
            "SELECT g.id, g.name, g.invite_code FROM web_member m JOIN web_group g ON g.id = m.group_id "
            "WHERE m.user_id = ? ORDER BY m.joined_at DESC",
            (user_id,),
        ).fetchall()
        return [{"id": r["id"], "name": r["name"], "inviteCode": r["invite_code"]} for r in rows]

    def new_access(self, member_id: int) -> str:
        """A fresh access token for this member (this browser's key to the space)."""
        token = secrets.token_urlsafe(32)
        with self._db:
            self._db.execute(
                "INSERT INTO web_access (token_hash, member_id, created_at) VALUES (?, ?, ?)",
                (hash_token(token), member_id, self._clock()),
            )
        return token
