"""
/coordinator slash commands, and install_coordinator() which adds them.

  /coordinator profile discipline skills weekly_hours   your own profile
  /coordinator kickoff text                             assignment -> charter card
  /coordinator plan                                     the project state, only for you

Switched off by default: install_coordinator() does nothing unless
MULCA_COORDINATOR_ENABLED is on, so without it MULCA is exactly as before.
MUCA-Server must run with MUCA_COORDINATOR_ENABLED too.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .bridge import CoordinatorBridge, answer_text
from .cards import CardButton

if TYPE_CHECKING:
    from ..runtime import BotManager

ENABLED_ENV_VAR = "MULCA_COORDINATOR_ENABLED"
TRUE_WORDS = frozenset({"1", "true", "yes", "on"})


def coordinator_enabled(env: Mapping[str, str] = os.environ) -> bool:
    return env.get(ENABLED_ENV_VAR, "").strip().lower() in TRUE_WORDS


def install_coordinator(
    manager: "BotManager",
    tree: app_commands.CommandTree,
    env: Mapping[str, str] = os.environ,
) -> CoordinatorBridge | None:
    """Add /coordinator and the card buttons, if switched on. Returns the bridge."""
    if not coordinator_enabled(env):
        return None
    bridge = CoordinatorBridge(manager)
    bridge.attach()
    CardButton.bridge = bridge
    # Like the lab's add_view: no API call, just the custom_id -> class mapping,
    # so cards posted before a restart answer again at once.
    manager.primary.client.add_dynamic_items(CardButton)
    bridge._buttons_on.add(id(manager.primary.client))
    tree.add_command(CoordinatorGroup(bridge))
    return bridge


class CoordinatorGroup(app_commands.Group):
    """/coordinator: for every member of a linked channel."""

    def __init__(self, bridge: CoordinatorBridge) -> None:
        super().__init__(name="coordinator", description="The group's project coordinator.")
        self._bridge = bridge

    @app_commands.command(name="profile", description="Save your profile for this project.")
    @app_commands.describe(
        discipline="What you study, e.g. Computer Engineering",
        skills="Comma separated, e.g. React, testing, writing",
        weekly_hours="Hours per week you can give the project",
    )
    async def profile(
        self,
        interaction: discord.Interaction,
        discipline: str = "",
        skills: str = "",
        weekly_hours: app_commands.Range[int, 0, 80] | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        answer = await self._bridge.send_command(
            interaction,
            "profile",
            {"discipline": discipline, "skills": skills, "weekly_hours": weekly_hours},
        )
        await interaction.followup.send(answer_text(answer), ephemeral=True)

    @app_commands.command(name="kickoff", description="Paste the assignment: the coordinator proposes the project charter.")
    @app_commands.describe(text="The text of the assignment (deliverables, deadlines)")
    async def kickoff(self, interaction: discord.Interaction, text: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        answer = await self._bridge.send_command(interaction, "kickoff", {"text": text})
        await interaction.followup.send(answer_text(answer), ephemeral=True)

    @app_commands.command(name="plan", description="Show the project state (only you see it).")
    async def plan(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        answer = await self._bridge.send_command(interaction, "state")
        if answer is None or answer.get("event") != "coordinator_state":
            await interaction.followup.send(answer_text(answer), ephemeral=True)
            return
        await interaction.followup.send(embed=state_embed(answer.get("state", {})), ephemeral=True)


def state_embed(state: dict) -> discord.Embed:
    """The project state as one private embed."""
    embed = discord.Embed(title="Coordinator · Project plan", colour=discord.Colour.blurple())
    charter = state.get("charter")
    embed.add_field(
        name="Goal",
        value=charter["goal"][:1000] if charter else "No charter yet: use /coordinator kickoff.",
        inline=False,
    )
    sections = {
        "Milestones": [f"{m['title']} — {m.get('due_date') or 'no date'}" for m in state.get("milestones", [])],
        "Members": [
            f"{m['display_name']}" + (f" · {m['discipline']}" if m.get("discipline") else "")
            for m in state.get("members", [])
        ],
        "Tasks": [f"{t['title']} · {t['status']}" for t in state.get("tasks", [])],
        "Decisions": [f"{d['question']} → {d['choice']}" for d in state.get("decisions", [])],
    }
    for name, lines in sections.items():
        value = "\n".join(f"• {line}" for line in lines)[:1000] or "—"
        embed.add_field(name=name, value=value, inline=False)
    return embed
