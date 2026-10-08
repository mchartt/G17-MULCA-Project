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

# The diary every participant fills in after a session -- same link for
# everyone, not per-deployment config, so it's a plain constant here rather
# than something an admin sets.
DIARY_FORM_URL = "https://forms.gle/ZSXMM9oFDFUUyU9HA"
DIARY_MESSAGE = (
    f"Please fill in your diary after this session: {DIARY_FORM_URL}\n\n"
    "Tip: react \N{THUMBS UP SIGN} to a MULCA text reply that was useful, "
    "or \N{THUMBS DOWN SIGN} to one that wasn't -- it helps us see what's "
    "working."
)


REGISTRATION_FORM_URL = "https://forms.gle/jhRZmGmtEvRNVpEUA"

# Posted to a channel's text channel when an admin links it (/mulca link,
# a brand-new link) or explicitly re-announces it (/mulca announce) --
# not per-message or per-day like DAILY_GREETING, since it's the same
# static explanation every time, not something worth repeating often.
INTRO_MESSAGE = (
    "**Welcome to your group's Discord channels!**\n\n"
    "Thank you for taking part in this study -- we really appreciate it.\n\n"
    "We believe Multi-User LLM-based Conversational Assistants (MULCAs) "
    "can be genuinely useful during group project work -- we're giving "
    "your team one, and using your experience to help us improve it. To "
    "make that work, please follow these guidelines:\n\n"
    "1. **Text channel** -- use it for anything you'd normally type to "
    "each other.\n"
    "2. **Voice channel** -- do all spoken discussion here, even if "
    "you're sitting together in person. Keeping the channel open gives "
    "MULCA the context it needs to respond more relevantly.\n"
    "3. **No other LLMs during collaborative tasks** -- please use only "
    "MULCA when working together as a group.\n"
    "4. **Individual tasks** -- try MULCA first. If it isn't enough and "
    "you need another LLM, note why in your diary.\n\n"
    f"If you haven't already, please complete the registration form: "
    f"{REGISTRATION_FORM_URL}. At the end of each session, fill in the "
    "short diary (find the link any time with `/diary`). At the end of "
    "the study, we'll send a post-study questionnaire.\n\n"
    "Type `/help` any time for a reminder of what MULCA is and how to "
    "talk to it."
)


# Posted once per linked conversation per day (BotRuntime.on_message, keyed
# on the first text message of the day), not per message -- so people see
# the usefulness-signal and diary reminders without having to remember to
# ask (/diary).
DAILY_GREETING = (
    "Welcome back! A quick reminder:\n\n"
    "During this session, please react to messages that were particularly "
    f"helpful or unhelpful with a \N{THUMBS UP SIGN} or \N{THUMBS DOWN SIGN}.\n\n"
    f"After this session, please fill in this form: {DIARY_FORM_URL}\n"
    "Let's get to it"
)


def _period(budget: Budget) -> tuple[str, str]:
    """("for today", "midnight"), ("for this week", "Monday") or the month's."""

    if budget.kind == "daily":
        return "for today", "midnight"
    if budget.kind == "weekly":
        return "for this week", "Monday"
    return "for this month", "the 1st of next month"


def _whose(budget: Budget) -> str:
    return "my usage limit" if budget.scope == "bot" else "MULCA's shared usage limit"


# The stage notices (usage.STAGES) never say what anything costs.


def limit_warning(budget: Budget) -> str:
    period, _ = _period(budget)
    return (
        f"Heads-up: I'm getting close to {_whose(budget)} {period}. If it "
        "keeps up, I'll first answer voice here in text, then take typed "
        "messages only."
    )


def listening_only(budget: Budget) -> str:
    period, until = _period(budget)
    return (
        f"To stay within {_whose(budget)} {period}, I'll keep listening in "
        f"voice but answer here in text until {until}."
    )


def text_only(budget: Budget) -> str:
    period, until = _period(budget)
    return (
        f"To stay within {_whose(budget)} {period}, I've left the voice "
        f"channel until {until}. Type here and I'll answer."
    )


def stage_lifted(level: int) -> str:
    """What a bot says when a limit resets or is raised, by the stage it's at now."""

    if level >= 3:
        return "I'm available again, in text only for now: type here and I'll answer."
    if level == 2:
        return "I'm back in voice: I'll listen there and answer here in text for now."
    return "I'm fully available again, voice included."


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

    def hold(self, problem: str, channel) -> None:
        """The problem holds too, but a later one already says it all."""

        self._active.setdefault(problem, (channel, ""))

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
            if problem not in skip and text:
                await post(channel, text)
