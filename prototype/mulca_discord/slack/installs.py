"""
The Slack workspaces Cadence was added to with the "Add to Slack" button.

One row per workspace: its bot token, saved by the web adapter when Slack
sends the member back after they allowed the app (web/connect_routes.py), and
read by the Slack channel (workspaces.py), which may run in another process.
Both open the same SQLite file (default_path), so on Render it lives in /data
and is kept across restarts like the rest of the data.

A token is a secret: it is written only here, never logged, never sent to the
browser. When a workspace removes the app, Slack says so ("app_uninstalled")
and the row is deleted.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS slack_install (
    team_id      TEXT PRIMARY KEY,
    team_name    TEXT NOT NULL,
    bot_token    TEXT NOT NULL,
    bot_user     TEXT NOT NULL,
    installed_at REAL NOT NULL
)
"""


@dataclass(frozen=True)
class Install:
    team_id: str
    team_name: str
    bot_token: str
    bot_user: str


def default_path() -> Path:
    """SLACK_INSTALLS_DB, else next to the web adapter's database (both processes agree)."""
    explicit = os.environ.get("SLACK_INSTALLS_DB")
    if explicit:
        return Path(explicit)
    return Path(os.environ.get("MULCA_WEB_DB", "data/web.sqlite3")).with_name("slack_installs.sqlite3")


class InstallStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute(SCHEMA)

    def _db(self) -> sqlite3.Connection:
        # A short connection each time: the other process may write in between.
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def save(self, install: Install) -> None:
        """A new or renewed install (adding the app again gives a new token)."""
        with self._db() as db:
            db.execute(
                "INSERT INTO slack_install (team_id, team_name, bot_token, bot_user, installed_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(team_id) DO UPDATE SET "
                "team_name = excluded.team_name, bot_token = excluded.bot_token, "
                "bot_user = excluded.bot_user, installed_at = excluded.installed_at",
                (install.team_id, install.team_name, install.bot_token, install.bot_user, time.time()),
            )

    def all(self) -> list[Install]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM slack_install ORDER BY installed_at").fetchall()
        return [Install(r["team_id"], r["team_name"], r["bot_token"], r["bot_user"]) for r in rows]

    def remove(self, team_id: str) -> bool:
        with self._db() as db:
            return db.execute("DELETE FROM slack_install WHERE team_id = ?", (team_id,)).rowcount > 0
