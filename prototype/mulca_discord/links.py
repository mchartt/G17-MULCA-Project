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

SCHEMA_VERSION = 8

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
    listening_mode TEXT NOT NULL DEFAULT '',
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
-- What each bot's sessions cost per local day, by what made the calls
-- ("main", "intervention", "transcription", "summary", "embedding"), as
-- MUCA-Server estimates it in its `usage` events (usage.py).
CREATE TABLE IF NOT EXISTS costs (
    bot_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    agent TEXT NOT NULL,
    fresh_text INTEGER NOT NULL DEFAULT 0,
    cached_text INTEGER NOT NULL DEFAULT 0,
    fresh_audio INTEGER NOT NULL DEFAULT 0,
    cached_audio INTEGER NOT NULL DEFAULT 0,
    out_text INTEGER NOT NULL DEFAULT 0,
    out_audio INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (bot_id, day, agent)
);
-- Usage limits, in USD (NULL: none). scope is "bot:<id>", "each" (every
-- bot without its own) or "pool" (all bots together).
CREATE TABLE IF NOT EXISTS limits (
    scope TEXT PRIMARY KEY,
    daily_usd REAL,
    weekly_usd REAL,
    monthly_usd REAL
);
-- The session reminder's own state (runtime.py's BotRuntime._greet_if_due
-- and _had_a_session), per conversation. Persisted, not in-memory only --
-- found live, a bot restart between /mulca greet and a conversation's
-- real first message reset this and let the reminder post again right
-- away. last_greeted_at is a Unix timestamp, 0 meaning "never" (including
-- "the cooldown clock hasn't started yet" -- see _greet_if_due).
CREATE TABLE IF NOT EXISTS greetings (
    conversation_id TEXT PRIMARY KEY,
    last_greeted_at REAL NOT NULL DEFAULT 0,
    had_a_session INTEGER NOT NULL DEFAULT 0
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
    # Per-link override of MUCA-Server's own MUCA_LISTENING_MODE default
    # (sent in the connect handshake, see muca_client.py) -- lets different
    # teams run different modes without a server-wide redeploy. "" means
    # unset: defer to the server's own default, same convention as
    # main_model/intervention_model below -- NOT "ambient", which would
    # always win over the server's setting even for a link nobody ever
    # explicitly chose a mode for (confirmed live: this was a real bug).
    listening_mode: str = ""

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
                listening_mode=row[6],
            )
            for row in self._db.execute(
                "SELECT text_channel_id, guild_id, bot_id, voice_channel_id, "
                "post_voice_transcripts, allow_dms, listening_mode FROM links"
            )
        }

        self._last_by_user: dict[int, int] = dict(
            self._db.execute("SELECT user_id, text_channel_id FROM last_link_by_user")
        )

        self._greetings: dict[str, tuple[float, bool]] = {
            row[0]: (row[1], bool(row[2]))
            for row in self._db.execute(
                "SELECT conversation_id, last_greeted_at, had_a_session "
                "FROM greetings"
            )
        }

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

        columns = {row[1] for row in self._db.execute("PRAGMA table_info(links)")}
        if "listening_mode" not in columns:
            # Version 4: no link had chosen one -- "" defers to the
            # server's own MUCA_LISTENING_MODE, not a hardcoded "ambient"
            # that would always win over it.
            self._db.execute(
                "ALTER TABLE links ADD COLUMN listening_mode TEXT NOT NULL "
                "DEFAULT ''"
            )

        columns = {row[1] for row in self._db.execute("PRAGMA table_info(limits)")}
        if "daily_minutes" in columns:
            # Version 5: limits were hours of active use, which don't convert
            # to money. They go, and the default dollar limits apply.
            self._db.executescript(
                "DROP TABLE limits; DROP TABLE IF EXISTS usage;" + _SCHEMA
            )

        columns = {row[1] for row in self._db.execute("PRAGMA table_info(greetings)")}
        if "last_greeted_at" not in columns:
            # Version 8: the reminder's cadence changed from "once per
            # calendar day" to "once per GREETING_COOLDOWN_SECONDS" --
            # last_greeted_date (a day string) doesn't carry over
            # meaningfully, so this starts every conversation's cooldown
            # fresh (0 = "never"), same as a brand-new row would.
            self._db.execute(
                "ALTER TABLE greetings ADD COLUMN last_greeted_at REAL "
                "NOT NULL DEFAULT 0"
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
                "voice_channel_id, post_voice_transcripts, allow_dms, "
                "listening_mode, created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (text_channel_id) DO UPDATE SET "
                "guild_id = excluded.guild_id, bot_id = excluded.bot_id, "
                "voice_channel_id = excluded.voice_channel_id, "
                "post_voice_transcripts = excluded.post_voice_transcripts, "
                "allow_dms = excluded.allow_dms, "
                "listening_mode = excluded.listening_mode",
                (
                    link.text_channel_id,
                    link.guild_id,
                    link.bot_id,
                    link.voice_channel_id,
                    int(link.post_voice_transcripts),
                    int(link.allow_dms),
                    link.listening_mode,
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

    def server_models(self) -> tuple[str, str]:
        """
        The (main, intervention) models last set for every bot with /mulca
        model; "" where none was, i.e. the server's own default applies.
        """

        saved = dict(
            self._db.execute(
                "SELECT key, value FROM meta WHERE key IN "
                "('server_main_model', 'server_intervention_model')"
            )
        )
        return saved.get("server_main_model", ""), saved.get("server_intervention_model", "")

    def set_server_models(self, main: str, intervention: str | None = None) -> None:
        """Remember the models set for every bot; the intervention one unless None."""

        with self._db:
            for key, value in (
                ("server_main_model", main),
                ("server_intervention_model", intervention),
            ):
                if value is not None:
                    self._db.execute(
                        "INSERT INTO meta (key, value) VALUES (?, ?) "
                        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                        (key, value),
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

    # -- the daily greeting/first-session reminder (runtime.py) -------------

    def greeting_state(self, conversation_id: str) -> tuple[float, bool]:
        """(last_greeted_at as a Unix timestamp, 0 if never; had_a_session)."""

        return self._greetings.get(conversation_id, (0.0, False))

    def set_greeting_state(
        self, conversation_id: str, *, last_greeted_at: float, had_a_session: bool
    ) -> None:
        self._greetings[conversation_id] = (last_greeted_at, had_a_session)
        with self._db:
            self._db.execute(
                "INSERT INTO greetings "
                "(conversation_id, last_greeted_at, had_a_session) "
                "VALUES (?, ?, ?) ON CONFLICT (conversation_id) DO UPDATE SET "
                "last_greeted_at = excluded.last_greeted_at, "
                "had_a_session = excluded.had_a_session",
                (conversation_id, last_greeted_at, int(had_a_session)),
            )

    # -- usage and limits (usage.py) ---------------------------------------

    def add_cost(
        self,
        bot_id: int,
        day: str,
        agent: str,
        tokens: tuple[int, int, int, int, int, int],
        cost_usd: float,
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO costs (bot_id, day, agent, fresh_text, cached_text, "
                "fresh_audio, cached_audio, out_text, out_audio, cost_usd) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (bot_id, day, agent) DO UPDATE SET "
                "fresh_text = fresh_text + excluded.fresh_text, "
                "cached_text = cached_text + excluded.cached_text, "
                "fresh_audio = fresh_audio + excluded.fresh_audio, "
                "cached_audio = cached_audio + excluded.cached_audio, "
                "out_text = out_text + excluded.out_text, "
                "out_audio = out_audio + excluded.out_audio, "
                "cost_usd = cost_usd + excluded.cost_usd",
                (bot_id, day, agent, *tokens, cost_usd),
            )

    def cost(self, bot_id: int | None, first_day: str, last_day: str) -> float:
        """
        A bot's spending over these days (inclusive) that counts against its
        limits; None: all bots. Memory summaries (agent "summary") don't
        count: a group shouldn't lose its voice, or its memory, to the
        upkeep of that memory. They still show in cost_details.
        """

        row = self._db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM costs "
            "WHERE day BETWEEN ? AND ? AND (? IS NULL OR bot_id = ?) "
            "AND agent != 'summary'",
            (first_day, last_day, bot_id, bot_id),
        ).fetchone()
        return row[0]

    def cost_details(
        self,
        bot_id: int,
        first_day: str,
        last_day: str,
    ) -> dict[str, tuple[int, int, int, int, int, int, float]]:
        """By agent: (fresh text, cached text, fresh audio, cached audio,
        text out, audio out, USD) over these days (inclusive)."""

        return {
            row[0]: tuple(row[1:])
            for row in self._db.execute(
                "SELECT agent, SUM(fresh_text), SUM(cached_text), "
                "SUM(fresh_audio), SUM(cached_audio), SUM(out_text), "
                "SUM(out_audio), SUM(cost_usd) FROM costs "
                "WHERE bot_id = ? AND day BETWEEN ? AND ? "
                "GROUP BY agent ORDER BY SUM(cost_usd) DESC",
                (bot_id, first_day, last_day),
            )
        }

    def limit(self, scope: str) -> tuple[float | None, float | None, float | None] | None:
        """(daily, weekly, monthly) USD for this scope, or None if it has none."""

        row = self._db.execute(
            "SELECT daily_usd, weekly_usd, monthly_usd FROM limits WHERE scope = ?",
            (scope,),
        ).fetchone()
        return tuple(row) if row else None

    def set_limit(
        self,
        scope: str,
        daily: float | None,
        weekly: float | None,
        monthly: float | None,
    ) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO limits (scope, daily_usd, weekly_usd, monthly_usd) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (scope) DO UPDATE SET "
                "daily_usd = excluded.daily_usd, "
                "weekly_usd = excluded.weekly_usd, "
                "monthly_usd = excluded.monthly_usd",
                (scope, daily, weekly, monthly),
            )

    def clear_limit(self, scope: str) -> None:
        with self._db:
            self._db.execute("DELETE FROM limits WHERE scope = ?", (scope,))
