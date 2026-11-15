"""
CoordinatorBridge: between Discord interactions and MUCA-Server's
coordinator events, for every linked channel of every bot.

Going out (a member acts):
    slash command / button  ->  send_command() / click()
        1. find the channel's link (BotManager.link_for_channel)
        2. open the group's one session (SessionRegistry.run) -- the same
           session the channel's messages use, never a second one
        3. send the roster, then the coordinator message, with a request id
        4. wait for the server's answer with that request id

Coming back (MUCA-Server answers), on_event():
    coordinator_notice / coordinator_state with a request id -> wakes step 4
    coordinator_proposal -> posts the card in the channel, or edits it in place

All Discord answers to members are ephemeral (only they see them), so the
channel only ever gets the cards themselves (project rule: no walls of text).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

import discord
from muca_server.protocol import CoordinatorCommandMessage, ProposalResponseMessage

from ..sessions import Scope
from .cards import card_view, proposal_embed

if TYPE_CHECKING:
    from ..runtime import BotManager, BotRuntime
    from ..links import Link
    from ..sessions import ScopeSession

logger = logging.getLogger(__name__)

# The kickoff waits for the model: give it time, then say so.
ANSWER_TIMEOUT_SECONDS = 60
NOT_LINKED = "The coordinator works only in a channel linked to MULCA."
NO_ANSWER = "The coordinator did not answer in time. Try again in a minute."


class CoordinatorBridge:
    def __init__(self, manager: "BotManager") -> None:
        self._manager = manager
        # request id -> future woken by the server's answer
        self._waiting: dict[str, asyncio.Future] = {}
        # proposal id -> the Discord message showing its card (this run only)
        self._cards: dict[str, discord.Message] = {}

    def attach(self) -> None:
        """Receive coordinator events from every bot's sessions."""
        for bot in self._manager.bots:
            bot.registry.on_coordinator_event = self.on_event

    # ------------------------------------------------------------------
    # Going out
    # ------------------------------------------------------------------

    async def send_command(
        self,
        interaction: discord.Interaction,
        command: str,
        args: dict[str, Any] | None = None,
    ) -> dict | None:
        """Run one coordinator command for the interaction's channel; the answer, or None."""
        request_id = uuid.uuid4().hex
        return await self._send(
            interaction,
            request_id,
            CoordinatorCommandMessage(
                event="coordinator_command",
                command=command,
                member_id=interaction.user.id,
                args=args or {},
                channel="discord",
                request_id=request_id,
            ),
        )

    async def click(self, interaction: discord.Interaction, action: str, proposal_id: str) -> None:
        """A card button: send the click, tell the member privately what happened."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        request_id = uuid.uuid4().hex
        answer = await self._send(
            interaction,
            request_id,
            ProposalResponseMessage(
                event="proposal_response",
                proposal_id=proposal_id,
                action=action,
                member_id=interaction.user.id,
                channel="discord",
                request_id=request_id,
            ),
        )
        # The card itself is redrawn by on_event (coordinator_proposal).
        await interaction.followup.send(answer_text(answer), ephemeral=True)

    async def _send(self, interaction: discord.Interaction, request_id: str, message) -> dict | None:
        found = self._manager.link_for_channel(interaction.channel_id or 0)
        if found is None:
            return {"event": "coordinator_notice", "ok": False, "text": NOT_LINKED}
        bot, link = found

        future = asyncio.get_running_loop().create_future()
        self._waiting[request_id] = future

        async def action(client) -> None:
            # The server checks clicks against this roster: send it first.
            await client.send_participants(bot.roster_text(link), modality="text")
            await client.send_coordinator(message)

        try:
            await bot.registry.run(
                scope_for(bot, link),
                action,
                reply_channel=bot.client.get_channel(link.text_channel_id),
                retry_once=False,  # a command must never run twice
            )
            return await asyncio.wait_for(future, ANSWER_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return None
        except Exception:
            logger.exception("Coordinator %s failed for %s", message.event, link.conversation_id)
            return None
        finally:
            self._waiting.pop(request_id, None)

    # ------------------------------------------------------------------
    # Coming back
    # ------------------------------------------------------------------

    async def on_event(self, session: "ScopeSession", data: dict) -> None:
        event = data.get("event")
        if event == "coordinator_proposal":
            await self._show_card(session, data.get("proposal", {}))
            return
        future = self._waiting.get(data.get("requestId", ""))
        if future is not None and not future.done():
            future.set_result(data)
        # A coordinator_state nobody waits for is for the web app: ignored here.

    async def _show_card(self, session: "ScopeSession", proposal: dict) -> None:
        """Edit the card if this run posted it; otherwise post it (e.g. after a restart)."""
        proposal_id = proposal.get("proposal_id", "")
        embed, view = proposal_embed(proposal), card_view(proposal)
        existing = self._cards.get(proposal_id)
        try:
            if existing is not None:
                await existing.edit(embed=embed, view=view)
                return
            channel = session.replies.channel
            if channel is None or proposal.get("status") != "pending":
                return  # nothing to show where no card was ever posted
            self._cards[proposal_id] = await channel.send(
                embed=embed, view=view or discord.utils.MISSING
            )
        except discord.HTTPException:
            logger.exception("Could not show coordinator card %s", proposal_id)


def scope_for(bot: "BotRuntime", link: "Link") -> Scope:
    """The link's group scope, built exactly like runtime.py builds it."""
    return Scope(
        conversation_id=link.conversation_id,
        bot_name=bot.name,
        listening_mode=link.listening_mode,
        channel_name=bot._channel_name_for(link),
        course=bot.course_for(link.guild_id),
    )


def answer_text(answer: dict | None) -> str:
    """What to tell the member: the server's notice, or that it did not answer."""
    if answer is None:
        return NO_ANSWER
    if answer.get("event") == "coordinator_notice":
        return answer.get("text") or ("Done." if answer.get("ok") else "Not done.")
    return "Done."
