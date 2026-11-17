"""
Slack user ids as the integers MUCA-Server wants.

MUCA-Server identifies a participant by an integer (protocol Participant.id);
Slack identifies a user by a string like "U07ABC12DEF". The string is read as
a base-36 number and moved above 2**62, a range no web member (1e8..1e9) and
no Discord member (snowflakes, far below 2**62 for decades) can have. So in a
linked group every member id still says which channel the member is in, and
the Slack id can be rebuilt from the integer to mention the person.
"""

from __future__ import annotations

from ..coordinator.texts import SLACK_ID_BASE, channel_of_member, member_name

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def member_id(slack_user: str) -> int:
    """ "U07ABC12DEF" -> an integer above 2**62."""
    return SLACK_ID_BASE + int(slack_user, 36)


def slack_user(member: int) -> str:
    """The inverse of member_id."""
    number = member - SLACK_ID_BASE
    text = ""
    while number:
        number, digit = divmod(number, 36)
        text = DIGITS[digit] + text
    return text


def who(member: int | None, names: dict | None = None) -> str:
    """A member written for Slack: a mention if they are on Slack, their name otherwise."""
    if not member:
        return ""
    if channel_of_member(member) == "slack":
        return f"<@{slack_user(member)}>"
    return member_name(member, names)
