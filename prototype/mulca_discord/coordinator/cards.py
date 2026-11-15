"""
How a coordinator proposal looks on Discord: an embed plus buttons.

The buttons are *persistent*: their custom_id carries the action and the
proposal id (`coord:confirm:<id>`), and `CardButton` is a
`discord.ui.DynamicItem` that discord.py matches against that pattern
(registered once with `client.add_dynamic_items`, see commands.py). So a
card posted before a bot restart keeps working after it, the same idea as
the lab's ListenView (commands.py, fixed custom_id + add_view).

Nothing here changes any state: a click only sends `proposal_response` to
MUCA-Server, which decides (bridge.py).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from .bridge import CoordinatorBridge

CUSTOM_ID = "coord:{action}:{proposal_id}"
CUSTOM_ID_PATTERN = r"coord:(?P<action>confirm|reject):(?P<proposal_id>[0-9a-f]{1,32})"

# Colours only add to the text: the status is always written in words too.
STATUS_COLOURS = {
    "pending": discord.Colour.blurple(),
    "applied": discord.Colour.green(),
    "rejected": discord.Colour.dark_grey(),
    "expired": discord.Colour.dark_grey(),
}
STATUS_WORDS = {
    "pending": "Waiting for a member to confirm",
    "applied": "Confirmed",
    "rejected": "Rejected",
    "expired": "Expired",
}
KIND_TITLES = {"charter": "Project charter"}


def proposal_embed(proposal: dict) -> discord.Embed:
    """The card's body: label, reason in italics, content, status in words."""
    status = proposal.get("status", "pending")
    payload = proposal.get("payload", {})
    embed = discord.Embed(
        title=f"Coordinator · {KIND_TITLES.get(proposal.get('kind'), 'Proposal')}",
        description=f"*{proposal.get('rationale') or 'Proposal from the coordinator.'}*",
        colour=STATUS_COLOURS.get(status, discord.Colour.blurple()),
    )
    if proposal.get("kind") == "charter":
        embed.add_field(name="Goal", value=_clip(payload.get("goal", "")), inline=False)
        embed.add_field(
            name="Deliverables",
            value=_clip(_bullets(payload.get("deliverables", []))),
            inline=False,
        )
        embed.add_field(
            name="Milestones",
            value=_clip(
                _bullets(
                    f"{m.get('title')} — {m.get('due_date') or 'no date'}"
                    for m in payload.get("milestones", [])
                )
            ),
            inline=False,
        )
    footer = STATUS_WORDS.get(status, status)
    if status == "pending" and proposal.get("expires_at"):
        expires = datetime.fromtimestamp(proposal["expires_at"], tz=timezone.utc)
        footer += f" · expires {expires:%d %b %H:%M} UTC"
    embed.set_footer(text=footer)
    return embed


def card_view(proposal: dict) -> discord.ui.View | None:
    """Confirm / Reject buttons while pending; no buttons once it is closed."""
    if proposal.get("status") != "pending":
        return None
    view = discord.ui.View(timeout=None)
    for action in ("confirm", "reject"):
        view.add_item(CardButton(action, proposal["proposal_id"]))
    return view


class CardButton(discord.ui.DynamicItem[discord.ui.Button], template=CUSTOM_ID_PATTERN):
    """One card button. Its custom_id is the whole state it needs."""

    # Set once by commands.install_coordinator: who handles the click.
    bridge: "CoordinatorBridge | None" = None

    def __init__(self, action: str, proposal_id: str) -> None:
        super().__init__(
            discord.ui.Button(
                label="Confirm" if action == "confirm" else "Reject",
                style=(
                    discord.ButtonStyle.success
                    if action == "confirm"
                    else discord.ButtonStyle.secondary
                ),
                custom_id=CUSTOM_ID.format(action=action, proposal_id=proposal_id),
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
        return cls(match["action"], match["proposal_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if CardButton.bridge is None:
            await interaction.response.send_message(
                "The coordinator is off.", ephemeral=True
            )
            return
        await CardButton.bridge.click(interaction, self.action, self.proposal_id)


def _bullets(items) -> str:
    lines = [f"• {item}" for item in items]
    return "\n".join(lines) if lines else "—"


def _clip(text: str, limit: int = 1000) -> str:
    """Discord refuses embed fields over 1024 characters."""
    text = text or "—"
    return text if len(text) <= limit else text[: limit - 1] + "…"
