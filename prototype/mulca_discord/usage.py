"""
How much each bot spends, against the limits an admin set (/mulca limit).

Spending is MUCA-Server's own estimate, which it sends after every provider
call a session makes (its `usage` event): this records it per bot, local day
and what made the call (the main agent, the observer, transcription, the
summarizer, embeddings).

Three limits apply to a bot, each in USD and daily, weekly and monthly: its
own ("bot:<id>", else the one for every bot, "each", else DEFAULT_LIMITS)
and the shared one of all bots together ("pool", by default POOL_FACTOR
times "each"). Days start at midnight in MULCA_TIMEZONE, weeks on Monday,
months on the 1st. As a bot gets through the tightest of them it goes
through STAGES (runtime.py): a heads-up, then replies in text while it still
listens in voice, then text only, then a full stop until that limit resets
or is raised. Spending is stored per day, so restarts never reset it.
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

# USD per day, week and month for every bot without a limit of its own.
DEFAULT_LIMITS = (30.0, 50.0, 100.0)

# The shared pool, when not set on its own: this many times "each".
POOL_FACTOR = 10

# The share of a limit that starts each stage: a heads-up, replies in text
# (still listening in voice), text only (out of voice), a full stop.
STAGES = (0.5, 0.7, 0.9, 1.0)
WARN, LISTEN, TEXT, STOP = 1, 2, 3, 4

KINDS = ("daily", "weekly", "monthly")

EACH = "each"
POOL = "pool"

# The order of a `usage` event's token counts, as stored.
TOKEN_FIELDS = (
    "freshText",
    "cachedText",
    "freshAudio",
    "cachedAudio",
    "outText",
    "outAudio",
)


def bot_scope(bot_id: int | None) -> str:
    return f"bot:{bot_id}"


@dataclass(frozen=True, slots=True)
class Budget:
    """One limit as it stands: kind "daily"/"weekly"/"monthly", scope "bot"/"pool"."""

    kind: str
    scope: str
    used: float
    limit: float
    resets_at: datetime

    @property
    def share(self) -> float:
        if self.limit <= 0:
            return float("inf")
        return self.used / self.limit


class UsageMeter:
    def __init__(self, store: LinkStore, *, tz: ZoneInfo | None = None) -> None:
        self._store = store
        self.tz = tz or ZoneInfo(os.environ.get(TIMEZONE_ENV_VAR, DEFAULT_TIMEZONE))

    def record(self, bot_id: int | None, usage: dict, now: float | None = None) -> None:
        """One `usage` event from MUCA-Server, for this bot, today."""

        if bot_id is None:
            return

        today = self._today(time.time() if now is None else now)
        self._store.add_cost(
            bot_id,
            today.isoformat(),
            str(usage.get("agent") or "unknown"),
            tuple(int(usage.get(name) or 0) for name in TOKEN_FIELDS),
            float(usage.get("costUsd") or 0.0),
        )

    def limits(self, bot_id: int | None) -> dict[str, tuple[float | None, ...]]:
        """The (daily, weekly, monthly) USD that apply to this bot, by scope."""

        each = self._store.limit(EACH) or DEFAULT_LIMITS
        own = self._store.limit(bot_scope(bot_id)) or each
        pool = self._store.limit(POOL) or tuple(
            None if usd is None else usd * POOL_FACTOR for usd in each
        )
        return {"bot": own, "pool": pool}

    def periods(self, now: float | None = None) -> dict[str, tuple[date, date]]:
        """Each kind's (first day, first day of the next one), today."""

        today = self._today(time.time() if now is None else now)
        monday = today - timedelta(days=today.weekday())
        first = today.replace(day=1)
        next_month = (first + timedelta(days=32)).replace(day=1)
        return {
            "daily": (today, today + timedelta(days=1)),
            "weekly": (monday, monday + timedelta(days=7)),
            "monthly": (first, next_month),
        }

    def budgets(self, bot_id: int | None, now: float | None = None) -> list[Budget]:
        periods = self.periods(now)
        today = periods["daily"][0]

        budgets = []
        for scope, limits in self.limits(bot_id).items():
            for kind, limit in zip(KINDS, limits):
                if limit is None:
                    continue
                first, next_first = periods[kind]
                used = self._store.cost(
                    bot_id if scope == "bot" else None,
                    first.isoformat(),
                    today.isoformat(),
                )
                resets_at = datetime(
                    next_first.year, next_first.month, next_first.day, tzinfo=self.tz
                )
                budgets.append(Budget(kind, scope, used, limit, resets_at))

        return budgets

    def stage(self, bot_id: int | None, now: float | None = None) -> tuple[int, Budget | None]:
        """
        How far this bot is through its budget: 0 (fine) to STOP, and the
        limit that put it there -- the most used one; at a tie, the one
        that resets last.
        """

        budget = max(
            self.budgets(bot_id, now),
            key=lambda b: (b.share, b.resets_at),
            default=None,
        )
        if budget is None:
            return 0, None

        level = sum(budget.share >= threshold for threshold in STAGES)
        return level, budget

    def details(self, bot_id: int, now: float | None = None) -> dict[str, dict]:
        """By kind (daily, weekly, monthly): this bot's costs by agent."""

        periods = self.periods(now)
        today = periods["daily"][0].isoformat()
        return {
            kind: self._store.cost_details(bot_id, first.isoformat(), today)
            for kind, (first, _) in periods.items()
        }

    def _today(self, now: float) -> date:
        return datetime.fromtimestamp(now, self.tz).date()
