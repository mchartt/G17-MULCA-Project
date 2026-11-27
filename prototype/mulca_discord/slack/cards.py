"""
How a coordinator card looks on Slack: Block Kit sections plus buttons.

The content (titles, fields, which buttons) comes from
coordinator/card_content.py, the same file Discord uses, so a card says the
same thing in every channel. Each button's action_id carries what the click
means: "coord:confirm:<proposal id>" or "coord:choose1:<proposal id>", the
same scheme as Discord's custom_id, so nothing has to be remembered between
the card being posted and the click (it also survives a restart).
"""

from __future__ import annotations

import re

from ..coordinator.card_content import (
    ABOUT_THE_CARD,
    BUTTON_LABELS,
    KIND_TITLES,
    OPTION_KINDS,
    actions_for,
    card_fields,
    card_title,
    clip,
    status_line,
)
from .ids import who

ACTION_ID = re.compile(r"^coord:(?P<action>confirm|reject|take|not_now|why|helpful|choose[0-2]):(?P<proposal_id>[0-9a-f]{1,32})$")
SECTION_LIMIT = 2900  # Slack refuses section texts over 3000 characters


QUOTE = re.compile(r"^&gt;(?= )", re.MULTILINE)


def escape(text: str) -> str:
    """
    Slack reads "<...>" as a link or a mention and "&" as an entity: a task
    titled "API <-> UI" or "R&D" would break or vanish. Its docs ask to write
    the three as &amp; &lt; &gt;. A "> " opening a line stays a quote ("Why?").
    """
    text = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return QUOTE.sub(">", text)


def to_mrkdwn(text: str, *, escaped: bool = False) -> str:
    """
    Our texts use **bold** (Discord, web); Slack writes it *bold*. The text is
    escaped first, unless it already was (a card, whose mentions are real).
    """
    return re.sub(r"\*\*(.+?)\*\*", r"*\1*", text if escaped else escape(text))


def _escaped(value):
    """A card's payload with every string escaped (ids and numbers untouched)."""
    if isinstance(value, str):
        return escape(value)
    if isinstance(value, list):
        return [_escaped(item) for item in value]
    if isinstance(value, dict):
        return {key: _escaped(item) for key, item in value.items()}
    return value


def card_text(proposal: dict) -> str:
    """The one-line version of the card (notifications, screen readers)."""
    return escape(f"Cadence · {card_title(proposal.get('kind'), proposal.get('payload', {}), proposal.get('status', 'pending'))}: {proposal.get('rationale') or ''}".strip())


def card_blocks(proposal: dict) -> list[dict]:
    """The card: title, reason in italics, content, status in words, buttons while pending."""
    kind = proposal.get("kind")
    status = proposal.get("status", "pending")
    payload = _escaped(proposal.get("payload", {}))
    names = _escaped(proposal.get("names"))
    rationale = escape(proposal.get("rationale") or "Proposal from Cadence.")
    blocks: list[dict] = [_section(f"*Cadence · {escape(card_title(kind, payload, status))}*\n_{rationale}_")]
    for name, value in card_fields(kind, payload, lambda member: who(member, names)):
        blocks.append(_section(f"*{name}*\n{to_mrkdwn(value, escaped=True) or '—'}"))
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": escape(status_line(proposal))}]})
    if status == "pending":
        blocks += _buttons(kind, payload, proposal["proposal_id"])
    return blocks


def _buttons(kind: str | None, payload: dict, proposal_id: str) -> list[dict]:
    """Answers on the first row; "about this card" (Why?, Helpful, Not now) on a second."""
    answers, about = [], []
    if kind in OPTION_KINDS:
        for n, option in enumerate(payload.get("options", [])[:3]):
            answers.append(_button(f"choose{n}", proposal_id, clip(option.get("label") or f"Option {n + 1}", 70), primary=True))
    for action in actions_for(kind, payload):
        button = _button(action, proposal_id, BUTTON_LABELS[action], primary=action in ("confirm", "take"))
        (about if action in ABOUT_THE_CARD else answers).append(button)
    return [{"type": "actions", "elements": row} for row in (answers, about) if row]


def _button(action: str, proposal_id: str, label: str, *, primary: bool) -> dict:
    button = {
        "type": "button",
        "action_id": f"coord:{action}:{proposal_id}",
        "text": {"type": "plain_text", "text": label, "emoji": False},
    }
    if primary:
        button["style"] = "primary"
    return button


def _section(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": clip(text, SECTION_LIMIT)}}
