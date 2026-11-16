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
    coordinator_mirror   -> a message written in a linked channel (web, Slack),
                            posted here as one line with the author's name

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

from ..sessions import Scope, SessionRegistry
from .cards import CardButton, card_view, proposal_embed, why_text
from .texts import mirror_text

if TYPE_CHECKING:
    from ..runtime import BotManager, BotRuntime
    from ..links import Link
    from ..sessions import ScopeSession

logger = logging.getLogger(__name__)

# The kickoff waits for the model: give it time, then say so.
ANSWER_TIMEOUT_SECONDS = 60
NOT_LINKED = "The coordinator works only in a channel linked to MULCA."
NO_ANSWER = (
    "The coordinator is still working. If it succeeds, the card appears in "
    "this channel: no need to try again."
)


class CoordinatorBridge:
    def __init__(self, manager: "BotManager") -> None:
        self._manager = manager
        # request id -> future woken by the server's answer
        self._waiting: dict[str, asyncio.Future] = {}
        # proposal id -> the Discord message showing its card (this run only)
        self._cards: dict[str, discord.Message] = {}
        # proposal id -> the last proposal seen, for "Why?" (this run only)
        self._proposals: dict[str, dict] = {}
        # Bot clients whose card buttons are registered (see _register_buttons).
        self._buttons_on: set[int] = set()

    def attach(self) -> None:
        """
        Receive coordinator events from every bot's sessions, including bots
        added later: the hook is set on the SessionRegistry class itself.
        """
        SessionRegistry.on_coordinator_event = self.on_event

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

    async def why(self, interaction: discord.Interaction, proposal_id: str) -> None:
        """
        "Why?": the strategy and the messages behind the card, privately.
        From memory when this run saw the card; after a bot restart, the card
        is asked to the server (command "card", no model, no state change).
        """
        proposal = self._proposals.get(proposal_id)
        if proposal is not None:
            await interaction.response.send_message(why_text(proposal), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        answer = await self.send_command(interaction, "card", {"proposal_id": proposal_id})
        proposal = (answer or {}).get("proposal")
        if proposal is not None:
            self._proposals[proposal_id] = proposal
            text = why_text(proposal)
        else:
            text = answer_text(answer) if answer and not answer.get("ok") else NO_ANSWER
        await interaction.followup.send(text, ephemeral=True)

    async def click(
        self,
        interaction: discord.Interaction,
        action: str,
        proposal_id: str,
        *,
        option: int | None = None,
    ) -> None:
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
                option=option,
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
        self._register_buttons(bot.client)

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

    def _register_buttons(self, client) -> None:
        """
        A card's clicks arrive on the client of the bot that posted it, so
        every bot that posts cards needs the button class registered (the
        primary bot already has it from install_coordinator).
        """
        if id(client) not in self._buttons_on:
            client.add_dynamic_items(CardButton)
            self._buttons_on.add(id(client))

    # ------------------------------------------------------------------
    # Coming back
    # ------------------------------------------------------------------

    async def on_event(self, session: "ScopeSession", data: dict) -> None:
        event = data.get("event")
        if event == "coordinator_proposal":
            await self._show_card(session, data.get("proposal", {}))
            return
        if event == "coordinator_mirror":
            await self._show_mirror(session, data)
            return
        future = self._waiting.get(data.get("requestId", ""))
        if future is not None and not future.done():
            future.set_result(data)
        # A coordinator_state nobody waits for is for the web app: ignored here.

    async def _show_mirror(self, session: "ScopeSession", data: dict) -> None:
        """Linked groups: show here what a member wrote in another channel."""
        channel = session.replies.channel
        if channel is None:
            return
        try:
            # No mentions: a mirrored "@everyone" must not ping this server.
            await channel.send(mirror_text(data), allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.exception("Could not mirror a message into %s", session.scope.conversation_id)

    async def _show_card(self, session: "ScopeSession", proposal: dict) -> None:
        """Edit the card if this run posted it; otherwise post it (e.g. after a restart)."""
        proposal_id = proposal.get("proposal_id", "")
        self._proposals[proposal_id] = proposal
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
