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
from typing import TYPE_CHECKING

import discord

from .card_content import (  # noqa: F401  (re-exported: tests and bridge.py import them from here)
    ABOUT_THE_CARD,
    KIND_TITLES,
    OPTION_KINDS,
    PROACTIVE_KINDS,
    STATUS_WORDS,
    STRATEGY_NAMES,
    actions_for,
    card_fields,
    card_title,
    clip,
    status_line,
    why_text,
)
from .texts import owner_text

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
        title=f"Cadence · {card_title(kind, payload, status)}",
        description=f"*{proposal.get('rationale') or 'Proposal from Cadence.'}*",
        colour=STATUS_COLOURS.get(status, discord.Colour.blurple()),
    )
    for name, value in card_fields(kind, payload, lambda member_id: owner_text(member_id, proposal.get("names"))):
        embed.add_field(name=name, value=clip(value), inline=False)
    embed.set_footer(text=status_line(proposal))
    return embed


def card_view(proposal: dict) -> discord.ui.View | None:
    """The buttons while pending; no buttons once it is closed."""
    if proposal.get("status") != "pending":
        return None
    kind = proposal.get("kind")
    payload = proposal.get("payload", {})
    proposal_id = proposal["proposal_id"]
    view = discord.ui.View(timeout=None)
    if kind in OPTION_KINDS:
        for n, option in enumerate(payload.get("options", [])[:3]):
            view.add_item(CardButton(f"choose{n}", proposal_id, label=option.get("label", f"Option {n + 1}")))
    actions = actions_for(kind, payload)
    for action in actions:
        # Second row for the "about this card" buttons, so the answers come first.
        view.add_item(CardButton(action, proposal_id, row=1 if action in ABOUT_THE_CARD else 0))
    return view


class CardButton(discord.ui.DynamicItem[discord.ui.Button], template=CUSTOM_ID_PATTERN):
    """One card button. Its custom_id is the whole state it needs."""

    # Set once by commands.install_coordinator: who handles the click.
    bridge: "CoordinatorBridge | None" = None

    def __init__(self, action: str, proposal_id: str, *, label: str | None = None, row: int | None = None) -> None:
        default_label, style = LABELS.get(action, (label or action, discord.ButtonStyle.primary))
        super().__init__(
            discord.ui.Button(
                label=clip(label or default_label, 80),
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
