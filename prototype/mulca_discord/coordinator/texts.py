"""
Plain-text views shared by the chat channels (Discord and Slack): the
catch-up answer, a mirrored message, and names for member ids.

Kept apart from bridge.py and from the Slack adapter so both write the same
words, and so the wording can be tested without Discord or Slack.
"""

from __future__ import annotations

from datetime import datetime

CHANNEL_NAMES = {"web": "Web", "discord": "Discord", "slack": "Slack"}
# Web members have ids in [1e8, 1e9) (web/store.py); Discord ids are far larger.
WEB_ID_MIN, WEB_ID_MAX = 100_000_000, 999_999_999
MAX_LINES = 12  # per channel, so the answer stays one readable message
MAX_CHARS = 1900  # Discord's limit for one message is 2000


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


def owner_text(owner_id: int | None, names: dict | None = None) -> str:
    """
    Who owns a task, written for Discord. A Discord member is mentioned as
    usual. In a linked group the owner can be a web member: their id means
    nothing on Discord, so their name is written instead (`names` is the
    id -> name map MUCA-Server sends with every card and state).
    """
    if not owner_id:
        return ""
    if WEB_ID_MIN <= owner_id <= WEB_ID_MAX:
        return (names or {}).get(str(owner_id), "a web member")
    return f"<@{owner_id}>"
