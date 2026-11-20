"""
Is a chat message meant for Cadence? Shared by the web, Discord and Slack
adapters (Matteo, 20/11: "Cadence" must answer when it is called by name,
with or without @, and understand that the next messages may be for it too).

    call(text)        -> (the message without Cadence's name, sure) if it
                         names Cadence as a call, None otherwise. sure=True
                         for a clear call: "@cadence ...", "Cadence, ...",
                         "hey cadence ...", "Cadence?", "Cadence come va?",
                         "... vero, Cadence?". sure=False when the name opens
                         or closes the message without the punctuation of a
                         call ("Cadence ieri ha risposto male.", "dobbiamo
                         migliorare Cadence?"): it may be talking ABOUT
                         Cadence, so it is offered as "maybe" and the server
                         lets Cadence stay silent (Matteo, 20/11).
                         A bare name in the middle of a sentence ("I told
                         Cadence yesterday") is never a call.
    addressed(text)   -> the text of call(), sure or not (older callers).
    FollowUps          after Cadence answered in a group, the next messages for
                         a short while may continue the talk: they are offered
                         to Cadence as "maybe" (the server lets it stay silent
                         when the members talk among themselves). A message
                         that @mentions or opens with another person's name is
                         for that person, never a follow-up.

Only routing: nothing here changes any state.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable

NAMES = r"(?:cadence|coordinator)"
FOLLOW_UP_SECONDS = 180

# "@cadence" / "@coordinator" anywhere in the message.
MENTION = re.compile(rf"@{NAMES}\b", re.IGNORECASE)
# The name at the start, as a call: "Cadence, ...", "hey cadence ...", "ok cadence: ...".
OPENING = re.compile(
    rf"^\s*(?:(?:hey|hi|hello|ciao|ehi|ei|ok|okay|scusa|sorry|dear)[\s,!]+)?@?{NAMES}\b[\s,:;!.?-]*",
    re.IGNORECASE,
)
# The name at the end, as a call: "... right, cadence?", "... vero Cadence?"
# ("... del coordinator." with a full stop and no comma is a statement: no call.)
CLOSING = re.compile(rf"(?:,\s*|\s+)@?{NAMES}\s*[?!]+\s*$|,\s*@?{NAMES}\s*\.?\s*$", re.IGNORECASE)
# The opening name followed by the punctuation of a call, or a greeting first.
SURE_OPENING = re.compile(
    rf"^\s*(?:(?:hey|hi|hello|ciao|ehi|ei|ok|okay|scusa|sorry|dear)[\s,!]+@?{NAMES}|@?{NAMES}\s*(?:[,:;!?]|$))",
    re.IGNORECASE,
)
# The message asks the other members, not Cadence ("secondo voi ... Cadence?",
# "ragazzi, ... cadence?"): a passing mention there is never offered to it (the
# live corpus of 20/11 showed the model answering these 2 times out of 3).
TO_THE_GROUP = re.compile(
    r"\b(secondo voi|che ne dite|cosa ne pensate|ragazzi|raga|voi che|what do you (all |guys )?think|guys|everyone|y'all)\b",
    re.IGNORECASE,
)
# Another person called: "@Bruno ..." or "Bruno, ..." at the start.
OTHER_MENTION = re.compile(rf"(?<![\w@])@(?!{NAMES}\b)[\w.-]+", re.IGNORECASE)
MAX_QUESTION_CHARS = 500


def call(text: str) -> tuple[str, bool] | None:
    """(the message without Cadence's name, sure) if it calls Cadence, else None."""
    if MENTION.search(text):
        rest, sure = MENTION.sub(" ", text), True
    elif OPENING.match(text):
        rest = OPENING.sub("", text, count=1)
        # "Cadence, ...", "ehi Cadence ...", "Cadence?" are calls; "Cadence <words>"
        # is one when it asks something ("cadence chi fa le API?"), else maybe.
        sure = bool(SURE_OPENING.match(text)) or text.rstrip().endswith("?")
    elif CLOSING.search(text):
        rest = CLOSING.sub("", text)
        rest = rest + ("?" if text.rstrip().endswith("?") and not rest.rstrip().endswith("?") else "")
        sure = bool(re.search(rf",\s*@?{NAMES}\s*[?!.]*\s*$", text, re.IGNORECASE))
    else:
        return None
    if not sure and TO_THE_GROUP.search(text):
        return None
    rest = " ".join(rest.split()).strip(" ,:;")
    return (rest or text.strip())[:MAX_QUESTION_CHARS], sure


def addressed(text: str) -> str | None:
    """The message without Cadence's name if it names Cadence as a call (sure or not), else None."""
    found = call(text)
    return found[0] if found else None


def calls_someone_else(text: str, member_names: Iterable[str]) -> bool:
    """True when the message @mentions another person or opens with a member's name ("Bruno, ...")."""
    if OTHER_MENTION.search(text):
        return True
    head = text.strip().lower()
    for name in member_names:
        first = name.strip().split(" ")[0].lower() if name.strip() else ""
        if first and re.match(rf"{re.escape(first)}\b[\s,:!]", head + " "):
            return True
    return False


class FollowUps:
    """When Cadence last answered in each group, to offer the next messages to it as "maybe"."""

    def __init__(self, *, window: float = FOLLOW_UP_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self._window = window
        self._clock = clock
        self._answered: dict[str, float] = {}

    def answered(self, group: str) -> None:
        """Cadence just answered in this group."""
        self._answered[group] = self._clock()

    def is_follow_up(self, group: str, text: str, member_names: Iterable[str] = ()) -> bool:
        at = self._answered.get(group)
        if at is None or self._clock() - at > self._window:
            return False
        return bool(text.strip()) and not calls_someone_else(text, member_names)
