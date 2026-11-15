"""
How a coordinator proposal looks on Discord: an embed plus buttons.

The buttons are *persistent*: their custom_id carries the action and the
proposal id (`coord:confirm:<id>`, `coord:choose1:<id>`), and `CardButton`
is a `discord.ui.DynamicItem` that discord.py matches against that pattern
(registered once with `client.add_dynamic_items`, see commands.py). So a
card posted before a bot restart keeps working after it, the same idea as
the lab's ListenView (commands.py, fixed custom_id + add_view).

Nothing here changes any state: a click only sends `proposal_response` to
MUCA-Server, which decides (bridge.py). "Why?" reads the reason the card
already carries (bridge.py `why`); only after a bot restart, when the card is
no longer in memory, it asks the server for it (command "card"). "Helpful"
is feedback: the server counts it and changes nothing (spec FR21).

Kinds (MUCA-Server docs/PROTOCOL.md, "Group Coordinator"):
    charter      Confirm, Reject                                  (M1, asked for)
    task_owner   Confirm (if an owner is suggested), I'll take it, Reject, Why?, Helpful, Not now
    delegation   I'll take it, Reject, Why?, Helpful, Not now
    decision     one button per option, Reject, Why?, Helpful, Not now
    blocker      Confirm, Reject, Why?, Helpful, Not now            (M4, CS7)
    plan         Confirm, Reject                                  (M4, /planning)
    checkin      one button per option, Reject                    (M4, /checkin)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from .bridge import CoordinatorBridge

CUSTOM_ID = "coord:{action}:{proposal_id}"
CUSTOM_ID_PATTERN = (
    r"coord:(?P<action>confirm|reject|take|not_now|why|helpful|choose[0-2]):(?P<proposal_id>[0-9a-f]{1,32})"
)

# Colours only add to the text: the status is always written in words too.
STATUS_COLOURS = {
    "pending": discord.Colour.blurple(),
    "applied": discord.Colour.green(),
    "rejected": discord.Colour.dark_grey(),
    "expired": discord.Colour.dark_grey(),
    "snoozed": discord.Colour.dark_grey(),
}
STATUS_WORDS = {
    "pending": "Waiting for a member to confirm",
    "applied": "Confirmed",
    "rejected": "Rejected",
    "expired": "Expired",
    "snoozed": "Not now: this suggestion is silenced for 30 minutes",
}
KIND_TITLES = {
    "charter": "Project charter",
    "task_owner": "Owner and date",
    "delegation": "One person can do this",
    "decision": "Close the decision",
    "plan": "Plan: who does what",
    "checkin": "Check-in",
    "blocker": "Something is blocked",
}
# Plain names of the strategies, for "Why?" (spec S5, S2, S3).
STRATEGY_NAMES = {
    "cs5_owner_and_date": "Owner and date (CS5): an agreed action had no owner or no date.",
    "cs2_delegate_simple_task": "Delegate simple tasks (CS2): several of you were discussing a task one person can do alone.",
    "cs3_close_decision": "Close the decision (CS3): the same question had two or more options and no decision.",
    "cs7_blockers_dependencies": "Blockers (CS7): someone is stuck or waiting on other work, and a deadline is at risk.",
}
PROACTIVE_KINDS = ("task_owner", "delegation", "decision", "blocker")
# The "about this card" buttons, on a second row so the answers come first.
ABOUT_THE_CARD = ("why", "helpful", "not_now")
LABELS = {
    "confirm": ("Confirm", discord.ButtonStyle.success),
    "take": ("I'll take it", discord.ButtonStyle.success),
    "reject": ("Reject", discord.ButtonStyle.secondary),
    "why": ("Why?", discord.ButtonStyle.secondary),
    "helpful": ("Helpful", discord.ButtonStyle.secondary),
    "not_now": ("Not now", discord.ButtonStyle.secondary),
}


def proposal_embed(proposal: dict) -> discord.Embed:
    """The card's body: label, reason in italics, content, status in words."""
    status = proposal.get("status", "pending")
    kind = proposal.get("kind")
    payload = proposal.get("payload", {})
    embed = discord.Embed(
        title=f"Coordinator · {KIND_TITLES.get(kind, 'Proposal')}",
        description=f"*{proposal.get('rationale') or 'Proposal from the coordinator.'}*",
        colour=STATUS_COLOURS.get(status, discord.Colour.blurple()),
    )
    for name, value in _fields(kind, payload):
        embed.add_field(name=name, value=_clip(value), inline=False)
    footer = STATUS_WORDS.get(status, status)
    if status == "pending" and proposal.get("expires_at"):
        expires = datetime.fromtimestamp(proposal["expires_at"], tz=timezone.utc)
        footer += f" · expires {expires:%d %b %H:%M} UTC"
    embed.set_footer(text=footer)
    return embed


def _fields(kind: str | None, payload: dict) -> list[tuple[str, str]]:
    """The content of each kind of card, as (field name, text)."""
    if kind == "charter":
        return [
            ("Goal", payload.get("goal", "")),
            ("Deliverables", _bullets(payload.get("deliverables", []))),
            (
                "Milestones",
                _bullets(f"{m.get('title')} — {m.get('due_date') or 'no date'}" for m in payload.get("milestones", [])),
            ),
        ]
    if kind in ("task_owner", "delegation"):
        fields = [("Task", payload.get("title", "")), ("By", payload.get("due_date") or "no date yet")]
        if kind == "task_owner":
            owner = payload.get("owner_id")
            fields.append(("Suggested owner", f"<@{owner}>" if owner else "nobody suggested: anyone can take it"))
        elif payload.get("return_to"):
            fields.append(("Then back to", payload["return_to"]))
        return fields
    if kind == "decision":
        options = payload.get("options", [])
        return [
            ("Question", payload.get("question", "")),
            (
                "Options",
                "\n".join(
                    f"**{n}. {o.get('label')}**" + (f" — {o['argument']}" if o.get("argument") else "")
                    for n, o in enumerate(options, start=1)
                ) or "—",
            ),
        ]
    if kind == "plan":
        return [
            (
                "Tasks",
                "\n".join(
                    f"• **{i.get('title')}** — "
                    + (f"<@{i['owner_id']}>" if i.get("owner_id") else "anyone")
                    + (f" · {i['due_date']}" if i.get("due_date") else "")
                    + (f"\n  _{i['reason']}_" if i.get("reason") else "")
                    for i in payload.get("items", [])
                ) or "—",
            )
        ]
    if kind == "checkin":
        return [
            ("What is late or at risk", _bullets(payload.get("findings", []))),
            ("Options", "\n".join(f"**{n}.** {o.get('label')}" for n, o in enumerate(payload.get("options", []), start=1)) or "—"),
        ]
    if kind == "blocker":
        fields = [("Task", payload.get("title", ""))]
        if payload.get("question"):
            fields.append(("Question", payload["question"]))
        if payload.get("helper_id"):
            fields.append(("Who could help", f"<@{payload['helper_id']}>"))
        return fields
    return []


def card_view(proposal: dict) -> discord.ui.View | None:
    """The buttons while pending; no buttons once it is closed."""
    if proposal.get("status") != "pending":
        return None
    kind = proposal.get("kind")
    payload = proposal.get("payload", {})
    proposal_id = proposal["proposal_id"]
    view = discord.ui.View(timeout=None)
    if kind in ("decision", "checkin"):
        for n, option in enumerate(payload.get("options", [])[:3]):
            view.add_item(CardButton(f"choose{n}", proposal_id, label=option.get("label", f"Option {n + 1}")))
    actions = {
        "charter": ["confirm", "reject"],
        "task_owner": (["confirm"] if payload.get("owner_id") else []) + ["take", "reject"],
        "delegation": ["take", "reject"],
        "decision": ["reject"],
        "checkin": ["reject"],
        "plan": ["confirm", "reject"],
        "blocker": ["confirm", "reject"],
    }.get(kind, ["confirm", "reject"])
    if kind in PROACTIVE_KINDS:
        actions += ["why", "helpful", "not_now"]
    for action in actions:
        # Second row for the "about this card" buttons, so the answers come first.
        view.add_item(CardButton(action, proposal_id, row=1 if action in ABOUT_THE_CARD else 0))
    return view


def why_text(proposal: dict | None) -> str:
    """What "Why?" shows, privately: the strategy and the messages behind the card."""
    context = (proposal or {}).get("payload", {}).get("context")
    if not context:
        return "This card was asked for by a member of the group."
    lines = [STRATEGY_NAMES.get(context.get("strategy_id"), context.get("strategy_id", ""))]
    lines.append(f"Topic: {context.get('topic', '')}")
    lines.append("Messages that made it step in:")
    lines += [f"> **{e.get('speaker')}**: {e.get('text')}" for e in context.get("evidence", [])]
    lines.append("If it is not useful now, press Not now: it stays silent on this topic for 30 minutes.")
    return _clip("\n".join(lines), 1900)


class CardButton(discord.ui.DynamicItem[discord.ui.Button], template=CUSTOM_ID_PATTERN):
    """One card button. Its custom_id is the whole state it needs."""

    # Set once by commands.install_coordinator: who handles the click.
    bridge: "CoordinatorBridge | None" = None

    def __init__(self, action: str, proposal_id: str, *, label: str | None = None, row: int | None = None) -> None:
        default_label, style = LABELS.get(action, (label or action, discord.ButtonStyle.primary))
        super().__init__(
            discord.ui.Button(
                label=_clip(label or default_label, 80),
                style=style,
                custom_id=CUSTOM_ID.format(action=action, proposal_id=proposal_id),
                row=row,
            )
        )
        self.action = action
        self.proposal_id = proposal_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> "CardButton":
        """Rebuild the button from its custom_id (also after a restart)."""
        return cls(match["action"], match["proposal_id"], label=getattr(item, "label", None))

    async def callback(self, interaction: discord.Interaction) -> None:
        if CardButton.bridge is None:
            await interaction.response.send_message("The coordinator is off.", ephemeral=True)
            return
        if self.action == "why":
            await CardButton.bridge.why(interaction, self.proposal_id)
            return
        action, option = split_action(self.action)
        await CardButton.bridge.click(interaction, action, self.proposal_id, option=option)


def split_action(action: str) -> tuple[str, int | None]:
    """"choose1" -> ("choose", 1); anything else -> (action, None)."""
    if action.startswith("choose"):
        return "choose", int(action[len("choose"):])
    return action, None


def _bullets(items) -> str:
    lines = [f"• {item}" for item in items]
    return "\n".join(lines) if lines else "—"


def _clip(text: str, limit: int = 1000) -> str:
    """Discord refuses embed fields over 1024 characters."""
    text = text or "—"
    return text if len(text) <= limit else text[: limit - 1] + "…"
