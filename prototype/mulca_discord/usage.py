"""
How much each bot is used, against the limits an admin set (/mulca limit).

Usage is counted in active minutes per channel: a channel (or DM) earns a
minute when, in that minute, someone wrote, someone held the floor in
voice, or MULCA replied. Channels add up -- two busy channels for an hour
use two hours -- and a silent voice call uses nothing.

Three limits apply to a bot, each optional, daily and weekly: its own
("bot:<id>", else the default for every bot, "each") and the shared one of
all bots together ("pool", by default POOL_FACTOR times "each"). Days start
at midnight in MULCA_TIMEZONE, weeks on Monday. Nothing but /mulca limit
changes a limit, and usage is stored per day, so restarts never reset it.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .links import LinkStore

TIMEZONE_ENV_VAR = "MULCA_TIMEZONE"
DEFAULT_TIMEZONE = "Europe/Rome"

# The shared pool, when not set on its own: this many times "each".
POOL_FACTOR = 10

# A heads-up is posted once this few minutes are left.
WARNING_MINUTES = 10

EACH = "each"
POOL = "pool"


def bot_scope(bot_id: int | None) -> str:
    return f"bot:{bot_id}"


@dataclass(frozen=True, slots=True)
class Budget:
    """One limit as it stands: kind "daily"/"weekly", scope "bot"/"pool"."""

    kind: str
    scope: str
    used: int
    limit: int
    resets_at: datetime

    @property
    def left(self) -> int:
        return max(0, self.limit - self.used)


class UsageMeter:
    def __init__(self, store: LinkStore, *, tz: ZoneInfo | None = None) -> None:
        self._store = store
        self.tz = tz or ZoneInfo(os.environ.get(TIMEZONE_ENV_VAR, DEFAULT_TIMEZONE))
        # The minute each channel was last counted for.
        self._counted: dict[str, int] = {}

    def mark_active(
        self,
        bot_id: int | None,
        conversation_id: str,
        now: float | None = None,
    ) -> bool:
        """Count this minute for the channel, once; True if it was new."""

        now = time.time() if now is None else now
        if bot_id is None or not self.is_new_minute(conversation_id, now):
            return False

        self._counted[conversation_id] = int(now // 60)
        self._store.add_active_minute(bot_id, self._today(now).isoformat())
        return True

    def is_new_minute(self, conversation_id: str, now: float | None = None) -> bool:
        """Whether this channel's activity now would count another minute."""

        now = time.time() if now is None else now
        return self._counted.get(conversation_id) != int(now // 60)

    def limits(self, bot_id: int | None) -> dict[str, tuple[int | None, int | None]]:
        """The (daily, weekly) minutes that apply to this bot, by scope."""

        applying = {}
        own = self._store.limit(bot_scope(bot_id)) or self._store.limit(EACH)
        if own is not None:
            applying["bot"] = own

        pool = self._store.limit(POOL)
        each = self._store.limit(EACH)
        if pool is None and each is not None:
            pool = tuple(
                None if minutes is None else minutes * POOL_FACTOR for minutes in each
            )
        if pool is not None:
            applying["pool"] = pool

        return applying

    def used(self, bot_id: int | None, now: float | None = None) -> tuple[int, int]:
        """A bot's (today, this week) active minutes; None: all bots."""

        today = self._today(time.time() if now is None else now)
        monday = today - timedelta(days=today.weekday())
        return (
            self._store.active_minutes(bot_id, today.isoformat(), today.isoformat()),
            self._store.active_minutes(bot_id, monday.isoformat(), today.isoformat()),
        )

    def budgets(self, bot_id: int | None, now: float | None = None) -> list[Budget]:
        now = time.time() if now is None else now
        today = self._today(now)
        monday = today - timedelta(days=today.weekday())
        periods = {
            "daily": (today, today + timedelta(days=1)),
            "weekly": (monday, monday + timedelta(days=7)),
        }

        budgets = []
        for scope, (daily, weekly) in self.limits(bot_id).items():
            for kind, limit in (("daily", daily), ("weekly", weekly)):
                if limit is None:
                    continue
                first, next_first = periods[kind]
                used = self._store.active_minutes(
                    bot_id if scope == "bot" else None,
                    first.isoformat(),
                    today.isoformat(),
                )
                resets_at = datetime(
                    next_first.year, next_first.month, next_first.day, tzinfo=self.tz
                )
                budgets.append(Budget(kind, scope, used, limit, resets_at))

        return budgets

    def check(self, bot_id: int | None, now: float | None = None) -> Budget | None:
        """The limit this bot is over, or None. The longest wait wins."""

        exceeded = [b for b in self.budgets(bot_id, now) if b.used >= b.limit]
        return max(exceeded, key=lambda b: b.resets_at, default=None)

    def tightest(self, bot_id: int | None, now: float | None = None) -> Budget | None:
        """The limit with the fewest minutes left, or None if there is none."""

        return min(self.budgets(bot_id, now), key=lambda b: b.left, default=None)

    def _today(self, now: float) -> date:
        return datetime.fromtimestamp(now, self.tz).date()
