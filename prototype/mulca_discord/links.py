"""
Which Discord channels each MULCA bot serves -- configured from Discord
(/mulca link, /mulca unlink), never in code or a config file.

A Link is one text channel, optionally one voice channel paired with it, and
the bot serving them. Its memory on MUCA-Server is keyed by the text
channel's id ("channel:<id>"), so it survives renaming the channel, swapping
its voice channel, or unlinking and linking it again later. Who takes part
isn't configured either: it's whoever can see the channel. DMs to the bot are
off unless an admin turns them on for a link (/mulca dms); then whoever can
see that link's text channel may DM the bot.

LinkStore keeps the links, the bots added with /mulca bot add (with their
tokens, unencrypted -- the file is readable only by the bot's own user), each
bot's paused state, where each user last spoke (what a DM from them gets
read access to), and each bot's usage and limits (usage.py) in a small SQLite file, on a volume, so all of it survives a
redeploy.
"""

from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

DB_PATH_ENV_VAR = "MULCA_DB_PATH"
DEFAULT_DB_PATH = "data/mulca.db"

SCHEMA_VERSION = 4

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bots (
    bot_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    paused INTEGER NOT NULL DEFAULT 0,
    main_model TEXT NOT NULL DEFAULT '',
    intervention_model TEXT NOT NULL DEFAULT '',
    token TEXT,
    added_by INTEGER,
    added_at REAL
);
CREATE TABLE IF NOT EXISTS links (
    text_channel_id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    bot_id INTEGER NOT NULL,
    voice_channel_id INTEGER UNIQUE,
    post_voice_transcripts INTEGER NOT NULL DEFAULT 0,
    allow_dms INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    created_at REAL
);
-- Discord lets a bot be in one voice channel per server at a time.
CREATE UNIQUE INDEX IF NOT EXISTS one_voice_per_bot_per_guild
    ON links (bot_id, guild_id) WHERE voice_channel_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS last_link_by_user (
    user_id INTEGER PRIMARY KEY,
    text_channel_id INTEGER NOT NULL
);
-- Active minutes per bot and local day (usage.py), summed over its channels.
CREATE TABLE IF NOT EXISTS usage (
    bot_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    active_minutes INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bot_id, day)
);
-- Usage limits, in minutes (NULL: none). scope is "bot:<id>", "each" (every
-- bot without its own) or "pool" (all bots together).
CREATE TABLE IF NOT EXISTS limits (
    scope TEXT PRIMARY KEY,
    daily_minutes INTEGER,
    weekly_minutes INTEGER
);
"""


def configured_db_path() -> Path:
    return Path(os.environ.get(DB_PATH_ENV_VAR) or DEFAULT_DB_PATH)


@dataclass(frozen=True, slots=True)
class BotRecord:
    """A bot added with /mulca bot add. Never log or show `token`."""

    bot_id: int
    name: str
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class Link:
    text_channel_id: int
    guild_id: int
    bot_id: int
    voice_channel_id: int | None = None
    post_voice_transcripts: bool = False
    # Whether people who can see this text channel may DM the bot.
    allow_dms: bool = False

    @property
    def conversation_id(self) -> str:
        return f"channel:{self.text_channel_id}"

    @property
    def name(self) -> str:
        """For logs and as a key: stable, unlike the channel's name."""

        return self.conversation_id

    def owns_channel(self, channel_id: int) -> bool:
        # Explicit "is not None" guard: without it, an unconfigured
        # voice_channel_id (None) would wrongly match a channel_id of None.
        return channel_id == self.text_channel_id or (
            self.voice_channel_id is not None
            and channel_id == self.voice_channel_id
        )


def link_for_channel(links: list[Link], channel_id: int) -> Link | None:
    for link in links:
        if link.owns_channel(channel_id):
            return link

    return None


class LinkStore:
    """
    The links, cached in memory and written through to SQLite. Writes are
    rare (an admin's command) and take milliseconds, so they run inline.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)

        self._db = sqlite3.connect(path)
        if str(path) != ":memory:":
            # It holds bot tokens: only the bot's own user may read it.
            os.chmod(path, 0o600)
        self._db.executescript(_SCHEMA)
        self._migrate()
        self._db.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        self._db.commit()

        self._links: dict[int, Link] = {
            row[0]: Link(
                text_channel_id=row[0],
                guild_id=row[1],
                bot_id=row[2],
                voice_channel_id=row[3],
                post_voice_transcripts=bool(row[4]),
                allow_dms=bool(row[5]),
            )
            for row in self._db.execute(
                "SELECT text_channel_id, guild_id, bot_id, voice_channel_id, "
                "post_voice_transcripts, allow_dms FROM links"
            )
        }

        self._last_by_user: dict[int, int] = dict(
            self._db.execute("SELECT user_id, text_channel_id FROM last_link_by_user")
        )

    def close(self) -> None:
        self._db.close()

    def _migrate(self) -> None:
        """Bring a file from an older version up to date, keeping its data."""

        columns = {row[1] for row in self._db.execute("PRAGMA table_info(links)")}
        if "allow_dms" not in columns:
            # Version 1: DMs weren't per link yet. They start off.
            self._db.execute(
                "ALTER TABLE links ADD COLUMN allow_dms INTEGER NOT NULL DEFAULT 0"
            )

        columns = {row[1] for row in self._db.execute("PRAGMA table_info(bots)")}
        if "main_model" not in columns:
            # Version 2: no bot had its own models. They start on the server's.
            for column in ("main_model", "intervention_model"):
                self._db.execute(
                    f"ALTER TABLE bots ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                )

    # -- links -------------------------------------------------------------

    def all_links(self) -> list[Link]:
        return list(self._links.values())

    def links_for(self, bot_id: int | None) -> list[Link]:
        return [link for link in self._links.values() if link.bot_id == bot_id]

    def link_for_channel(self, channel_id: int) -> Link | None:
        return link_for_channel(self.all_links(), channel_id)

    def conflicts(self, link: Link) -> list[str]:
        """
        Why `link` can't be saved as it stands; empty if it can. Saving a
        link whose text channel is already linked to the same bot updates
        it (e.g. to add or swap its voice channel).
        """

        problems: list[str] = []

        existing = self._links.get(link.text_channel_id)
        if existing is not None and existing.bot_id != link.bot_id:
            problems.append(
                f"<#{link.text_channel_id}> is already served by another "
                "MULCA bot; unlink it first."
            )

        if link.voice_channel_id is not None:
            voice_owner = self.link_for_channel(link.voice_channel_id)
            if (
                voice_owner is not None
                and voice_owner.text_channel_id != link.text_channel_id
            ):
                problems.append(
                    f"<#{link.voice_channel_id}> is already linked to "
                    f"<#{voice_owner.text_channel_id}>."
                )

            for other in self.links_for(link.bot_id):
                if (
                    other.guild_id == link.guild_id
                    and other.voice_channel_id is not None
                    and other.text_channel_id != link.text_channel_id
                ):
                    problems.append(
                        "This bot already has a voice channel in this server "
                        f"(<#{other.voice_channel_id}>, for "
                        f"<#{other.text_channel_id}>), and Discord lets a bot "
                        "be in only one voice channel per server. Use another "
                        "bot, or link this channel without voice."
                    )

        text_owner = self.link_for_channel(link.text_channel_id)
        if (
            text_owner is not None
            and text_owner.text_channel_id != link.text_channel_id
        ):
            problems.append(
                f"<#{link.text_channel_id}> is the voice channel of "
                f"<#{text_owner.text_channel_id}>."
            )

        return problems

    def save(self, link: Link, *, created_by: int | None = None) -> Link | None:
        """Add or update a link; returns the one it replaced, if any."""

        problems = self.conflicts(link)
        if problems:
            raise ValueError(" ".join(problems))

        previous = self._links.get(link.text_channel_id)
        with self._db:
            self._db.execute(
                "INSERT INTO links (text_channel_id, guild_id, bot_id, "
                "voice_channel_id, post_voice_transcripts, allow_dms, created_by, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (text_channel_id) DO UPDATE SET "
                "guild_id = excluded.guild_id, bot_id = excluded.bot_id, "
                "voice_channel_id = excluded.voice_channel_id, "
                "post_voice_transcripts = excluded.post_voice_transcripts, "
                "allow_dms = excluded.allow_dms",
                (
                    link.text_channel_id,
                    link.guild_id,
                    link.bot_id,
                    link.voice_channel_id,
                    int(link.post_voice_transcripts),
                    int(link.allow_dms),
                    created_by,
                    time.time(),
                ),
            )
        self._links[link.text_channel_id] = link
        return previous

    def remove(self, channel_id: int) -> Link | None:
        """Unlink the link owning this channel (text or voice), if any."""

        link = self.link_for_channel(channel_id)
        if link is None:
            return None

        with self._db:
            self._db.execute(
                "DELETE FROM links WHERE text_channel_id = ?",
                (link.text_channel_id,),
            )
        del self._links[link.text_channel_id]
        return link

    # -- bots ----------------------------------------------------------------

    def register_bot(self, bot_id: int, name: str, *, is_primary: bool) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO bots (bot_id, name, is_primary, added_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (bot_id) DO UPDATE SET name = excluded.name, "
                "is_primary = excluded.is_primary",
                (bot_id, name, int(is_primary), time.time()),
            )

    def add_bot(self, record: BotRecord, *, added_by: int | None = None) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO bots (bot_id, name, is_primary, token, added_by, added_at) "
                "VALUES (?, ?, 0, ?, ?, ?) "
                "ON CONFLICT (bot_id) DO UPDATE SET name = excluded.name, "
                "token = excluded.token",
                (record.bot_id, record.name, record.token, added_by, time.time()),
            )

    def remove_bot(self, bot_id: int) -> None:
        with self._db:
            self._db.execute("DELETE FROM bots WHERE bot_id = ?", (bot_id,))

    def added_bots(self) -> list[BotRecord]:
        """The bots added with /mulca bot add, which this process starts."""

        return [
            BotRecord(bot_id=row[0], name=row[1], token=row[2])
            for row in self._db.execute(
                "SELECT bot_id, name, token FROM bots "
                "WHERE is_primary = 0 AND token IS NOT NULL ORDER BY added_at"
            )
        ]

    def has_bot(self, bot_id: int) -> bool:
        return (
            self._db.execute(
                "SELECT 1 FROM bots WHERE bot_id = ? AND (is_primary = 1 OR token IS NOT NULL)",
                (bot_id,),
            ).fetchone()
            is not None
        )

    def has_token(self, token: str) -> bool:
        return (
            self._db.execute("SELECT 1 FROM bots WHERE token = ?", (token,)).fetchone()
            is not None
        )

    def models_for(self, bot_id: int | None) -> tuple[str, str]:
        """A bot's own (main, intervention) realtime models; "" is the server's."""

        row = self._db.execute(
            "SELECT main_model, intervention_model FROM bots WHERE bot_id = ?",
            (bot_id,),
        ).fetchone()
        return (row[0], row[1]) if row else ("", "")

    def set_models(self, bot_id: int, main: str, intervention: str | None = None) -> None:
        """Set a bot's main model, and its intervention model unless None."""

        with self._db:
            self._db.execute(
                "UPDATE bots SET main_model = ?, "
                "intervention_model = COALESCE(?, intervention_model) "
                "WHERE bot_id = ?",
                (main, intervention, bot_id),
            )

    def is_paused(self, bot_id: int) -> bool:
        row = self._db.execute(
            "SELECT paused FROM bots WHERE bot_id = ?",
            (bot_id,),
        ).fetchone()
        return bool(row and row[0])

    def set_paused(self, bot_id: int, paused: bool) -> None:
        with self._db:
            self._db.execute(
                "UPDATE bots SET paused = ? WHERE bot_id = ?",
                (int(paused), bot_id),
            )

    # -- who spoke where -------------------------------------------------------

    def remember_speaker(self, user_id: int, text_channel_id: int) -> None:
        # Called on every message: only write when it changes.
        if self._last_by_user.get(user_id) == text_channel_id:
            return

        self._last_by_user[user_id] = text_channel_id
        with self._db:
            self._db.execute(
                "INSERT INTO last_link_by_user (user_id, text_channel_id) "
                "VALUES (?, ?) ON CONFLICT (user_id) DO UPDATE SET "
                "text_channel_id = excluded.text_channel_id",
                (user_id, text_channel_id),
            )

    def last_link_for(self, user_id: int) -> Link | None:
        text_channel_id = self._last_by_user.get(user_id)
        return self._links.get(text_channel_id) if text_channel_id else None

    # -- usage and limits (usage.py) ---------------------------------------

    def add_active_minute(self, bot_id: int, day: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO usage (bot_id, day, active_minutes) VALUES (?, ?, 1) "
                "ON CONFLICT (bot_id, day) DO UPDATE SET "
                "active_minutes = active_minutes + 1",
                (bot_id, day),
            )

    def active_minutes(self, bot_id: int | None, first_day: str, last_day: str) -> int:
        """A bot's active minutes over these days (inclusive); None: all bots."""

        row = self._db.execute(
            "SELECT COALESCE(SUM(active_minutes), 0) FROM usage "
            "WHERE day BETWEEN ? AND ? AND (? IS NULL OR bot_id = ?)",
            (first_day, last_day, bot_id, bot_id),
        ).fetchone()
        return row[0]

    def limit(self, scope: str) -> tuple[int | None, int | None] | None:
        """(daily, weekly) minutes for this scope, or None if it has none."""

        row = self._db.execute(
            "SELECT daily_minutes, weekly_minutes FROM limits WHERE scope = ?",
            (scope,),
        ).fetchone()
        return (row[0], row[1]) if row else None

    def set_limit(self, scope: str, daily: int | None, weekly: int | None) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO limits (scope, daily_minutes, weekly_minutes) "
                "VALUES (?, ?, ?) ON CONFLICT (scope) DO UPDATE SET "
                "daily_minutes = excluded.daily_minutes, "
                "weekly_minutes = excluded.weekly_minutes",
                (scope, daily, weekly),
            )

    def clear_limit(self, scope: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM limits WHERE scope = ?", (scope,))
