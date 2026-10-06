"""
What MULCA tells users about itself, rather than about the conversation:
limits, being offline or paused, and the like -- all the text in one place.

Each problem is announced exactly once, when it is raised, in the channel
where it showed up (Notices). After that MULCA stays quiet about it, unless
someone @mentions it while the problem holds: then it says it again.
"""

from __future__ import annotations

import logging

from .usage import Budget

logger = logging.getLogger(__name__)

# The answer to a DM the bot doesn't take.
DMS_OFF = (
    "I don't take direct messages here. Talk to me in a server channel I'm "
    "in -- or ask a server admin to turn DMs on for that channel (/mulca dms)."
)

OFFLINE = "I'm offline right now and can't answer. Please try again in a few minutes."
BACK_ONLINE = "I'm back online."
AVAILABLE_AGAIN = "I'm available again."
PAUSED = "I'm paused by a server admin and won't answer until I'm started again."
TURN_FAILED = "Sorry, something went wrong and I couldn't answer that. Please try again."
ATTACHMENTS = "I can only read text messages -- I can't see attachments, images or stickers."


def _period(budget: Budget) -> tuple[str, str]:
    """("for today", "midnight") or ("for this week", "Monday")."""

    if budget.kind == "daily":
        return "for today", "midnight"
    return "for this week", "Monday"


def limit_warning(budget: Budget) -> str:
    period, until = _period(budget)
    return (
        f"Heads-up: I have about {budget.left} minutes left {period}. "
        f"After that I'll take a break until {until}."
    )


def limit_reached(budget: Budget) -> str:
    period, until = _period(budget)
    who = (
        "I've reached my usage limit"
        if budget.scope == "bot"
        else "MULCA has reached its shared usage limit"
    )
    return (
        f"{who} {period}, so I'm taking a break until {until}. "
        "A server admin can change this with `/mulca limit`."
    )


def voice_join_failed(voice_channel_id: int, permissions: list[str]) -> str:
    missing = ", ".join(f"*{name}*" for name in permissions)
    return (
        f"I couldn't join <#{voice_channel_id}>: I'm missing the {missing} "
        "permission. A server admin can fix that."
    )


async def post(channel, text: str) -> bool:
    if channel is None:
        return False

    try:
        await channel.send(text)
        return True
    except Exception:
        logger.warning("Could not post a notice in %s", channel, exc_info=True)
        return False


class Notices:
    """One bot's problems that hold right now, each announced once."""

    def __init__(self) -> None:
        # problem -> (channel it was announced in, text)
        self._active: dict[str, tuple[object, str]] = {}

    def is_active(self, problem: str) -> bool:
        return problem in self._active

    def text(self, problem: str) -> str | None:
        entry = self._active.get(problem)
        return entry[1] if entry else None

    async def raise_(self, problem: str, channel, text: str) -> bool:
        """Announce the problem, unless it already holds. True if it's new."""

        if problem in self._active:
            return False

        self._active[problem] = (channel, text)
        await post(channel, text)
        return True

    async def resolve(self, problem: str, text: str | None = None) -> None:
        """The problem is over; say `text` where it was announced, if given."""

        entry = self._active.pop(problem, None)
        if entry is not None and text:
            await post(entry[0], text)

    def forget(self, problem: str) -> None:
        """The problem is over, and there's nothing to say about it."""

        self._active.pop(problem, None)

    async def remind(self, channel, *, skip: tuple[str, ...] = ()) -> None:
        """For an @mention: every problem that still holds, again."""

        for problem, (_, text) in list(self._active.items()):
            if problem not in skip:
                await post(channel, text)
