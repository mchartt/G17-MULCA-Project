"""
Plain-text views shared by the chat channels (Discord and Slack): the
catch-up answer, a mirrored message, and names for member ids.

Kept apart from bridge.py and from the Slack adapter so both write the same
words, and so the wording can be tested without Discord or Slack.
"""

from __future__ import annotations

from datetime import datetime

CHANNEL_NAMES = {"web": "Web", "discord": "Discord", "discord_voice": "Discord voice", "slack": "Slack"}
# Which channel a member id comes from, by its size:
#   web      [1e8, 1e9)        (web/store.py)
#   Discord  snowflakes, today around 1e18, below 2**62 until about 2049
#   Slack    2**62 + the user id read as a base-36 number (slack/ids.py)
WEB_ID_MIN, WEB_ID_MAX = 100_000_000, 999_999_999
SLACK_ID_BASE = 1 << 62
MAX_LINES = 12  # per channel, so the answer stays one readable message
MAX_CHARS = 1900  # Discord's limit for one message is 2000


def day(value: str | None, today=None) -> str:
    """
    A date as people write it: "2026-11-28" -> "28 Nov" (with the year when it
    is not this year's). Anything that is not an ISO date is shown as it is.
    The web app writes dates the same way on its cards.
    """
    if not value:
        return ""
    try:
        when = datetime.strptime(str(value)[:10], "%Y-%m-%d")
    except ValueError:
        return str(value)
    this_year = (today or datetime.now()).year
    return f"{when.day} {when:%b}" + ("" if when.year == this_year else f" {when.year}")


def channel_name(channel: str) -> str:
    return CHANNEL_NAMES.get(channel, channel.capitalize() or "Another channel")


def mirror_text(data: dict) -> str:
    """A message written in another channel, as one line here."""
    name = data.get("speakerName") or "A member"
    return f"**{name}** · {channel_name(data.get('channel', ''))}: {data.get('text', '')}"[:MAX_CHARS]


def catchup_text(answer: dict | None) -> str:
    """The catch-up as text: the summary line, the decisions, then each channel."""
    if not answer:
        return "The coordinator did not answer. Try again in a minute."
    catchup = answer.get("catchup")
    lines = [answer.get("text") or "Catch-up"]
    if not catchup:
        return lines[0]
    if not catchup.get("linked"):
        lines.append("To link this channel to your web space, run `/coordinator link` with the space's invite code.")
    for decision in catchup.get("decisions", []):
        reason = f" ({decision['reason']})" if decision.get("reason") else ""
        lines.append(f"• Decided: {decision['question']} → **{decision['choice']}**{reason}")
    for place in catchup.get("elsewhere", []):
        messages = place.get("messages", [])
        if not messages:
            continue
        lines.append(f"\n**On {channel_name(place.get('channel', ''))}**")
        hidden = place.get("total", len(messages)) - min(len(messages), MAX_LINES)
        if hidden > 0:
            lines.append(f"_{hidden} earlier messages not shown_")
        for message in messages[-MAX_LINES:]:
            when = datetime.fromtimestamp(message.get("at", 0)).strftime("%a %H:%M")
            lines.append(f"{when} · {message.get('speaker', 'member')}: {message.get('text', '')}")
    return "\n".join(lines)[:MAX_CHARS]


def channel_of_member(member_id: int) -> str:
    if WEB_ID_MIN <= member_id <= WEB_ID_MAX:
        return "web"
    return "slack" if member_id >= SLACK_ID_BASE else "discord"


def member_name(member_id: int, names: dict | None) -> str:
    """The member's name from the id -> name map MUCA-Server sends with every card and state."""
    return (names or {}).get(str(member_id)) or f"a {channel_name(channel_of_member(member_id))} member"


def owner_text(owner_id: int | None, names: dict | None = None) -> str:
    """
    Who owns a task, written for Discord. A Discord member is mentioned as
    usual. In a linked group the owner can be a web or Slack member: their id
    means nothing on Discord, so their name is written instead.
    """
    if not owner_id:
        return ""
    if channel_of_member(owner_id) == "discord":
        return f"<@{owner_id}>"
    return member_name(owner_id, names)
