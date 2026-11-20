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
                         The name anywhere else ("I told Cadence yesterday",
                         "secondo me Cadence è inutile") is a "maybe" too: the
                         server decides, and stays silent when it is only
                         talked about (Matteo, 20/11).
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

# A greeting before the name, letters stretched as people type them: "Oii
# Cadence, sono al 30%" was not a call on 20/11 (only "ei" / "ehi" were), so
# it went to the lab's agent and Cadence never answered it.
GREETING = r"(?:h+e+y+|h+i+|hello+|c+i+a+o+|e+h+i+|e+i+|o+i+|yo+|ok|okay|scusa|sorry|dear|buongiorno|buonasera|salve)"
# "@cadence" / "@coordinator" anywhere in the message.
MENTION = re.compile(rf"(?<![\w.])@{NAMES}\b", re.IGNORECASE)  # not an e-mail address
# The name at the start, as a call: "Cadence, ...", "hey cadence ...", "ok cadence: ...".
OPENING = re.compile(
    rf"^\s*(?:{GREETING}[\s,!]+)?@?{NAMES}\b[\s,:;!.?-]*",
    re.IGNORECASE,
)
# The name at the end, as a call: "... right, cadence?", "... vero Cadence?"
# ("... del coordinator." with a full stop and no comma is a statement: no call.)
CLOSING = re.compile(rf"(?:,\s*|\s+)@?{NAMES}\s*[?!]+\s*$|,\s*@?{NAMES}\s*\.?\s*$", re.IGNORECASE)
# The opening name followed by the punctuation of a call, or a greeting first.
SURE_OPENING = re.compile(
    # \b, not a raw backspace: until 20/11 the file held a 0x08 byte here, so a
    # greeting + "Cadence" never counted as a sure call.
    rf"^\s*(?:{GREETING}[\s,!]+@?{NAMES}\b|@?{NAMES}\s*(?:[,:;!?]|$))",
    re.IGNORECASE,
)
# The message asks the other members, not Cadence ("secondo voi ... Cadence?",
# "ragazzi, ... cadence?"): a passing mention there is never offered to it (the
# live corpus of 20/11 showed the model answering these 2 times out of 3).
TO_THE_GROUP = re.compile(
    r"\b(secondo voi|che ne dite|cosa ne pensate|ragazzi|raga|voi che|what do you (all |guys )?think|guys|everyone|y'all)\b",
    re.IGNORECASE,
)
# "Cadence" anywhere else in the message (Matteo, 20/11: Cadence must notice by
# itself that it is being talked to, and stay silent when the group only talks
# ABOUT it: "Cadence è troppo forte", "secondo me Cadence è inutile"). Offered
# as "maybe": the server's model answers or stays silent. Only the product name:
# "coordinator" in the middle of a sentence is an ordinary word.
ANYWHERE = re.compile(r"(?<![\w@.])cadence\b", re.IGNORECASE)
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
    elif ANYWHERE.search(text):
        rest, sure = text, False
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


def for_cadence(
    text: str, *, follow_ups: FollowUps, place: str, member_names: Iterable[str] = (), tagged: bool = False
) -> tuple[str, bool] | None:
    """
    The one routing rule of every channel (web, Discord, Slack): (what to ask
    Cadence, maybe) when the message is for Cadence or might be, else None.

        tagged (an @mention of the bot) or a clear call  -> (question, False)
        the name anywhere else                           -> (whole message, True)
        right after Cadence answered in `place`          -> (whole message, True)

    "maybe" lets the server's model stay silent (talk ABOUT Cadence, members
    talking among themselves).
    """
    called = call(text)
    if called and called[1]:
        return called[0], False
    if tagged:
        return " ".join(text.split())[:MAX_QUESTION_CHARS], False
    if called:
        return text.strip()[:MAX_QUESTION_CHARS], True
    if follow_ups.is_follow_up(place, text, member_names):
        return text.strip()[:MAX_QUESTION_CHARS], True
    return None
