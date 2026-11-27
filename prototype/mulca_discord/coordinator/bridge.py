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
import dataclasses
import logging
import uuid
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import discord
from muca_server.protocol import CoordinatorCommandMessage, ProposalResponseMessage

from ..addressing import FollowUps, for_cadence
from ..invites import invite_in
from ..links import Link
from ..sessions import Scope, SessionRegistry
from .cards import CardButton, card_view, proposal_embed, why_text
from .texts import mirror_text

if TYPE_CHECKING:
    from ..runtime import BotManager, BotRuntime
    from ..sessions import ScopeSession

# Said in the channel right after a pasted invite link linked it: what to do next, in one line.
LINKED_NEXT = (
    "Next: talk here as usual and I suggest owners, dates and decisions as cards. "
    "In a voice call, `/coordinator voice` lets me listen and keep the transcript. `/coordinator help` lists the rest."
)

logger = logging.getLogger(__name__)

# The kickoff waits for the model: give it time, then say so.
ANSWER_TIMEOUT_SECONDS = 60
NOT_LINKED = "The coordinator works only in a channel linked to MULCA."
NO_ANSWER = (
    "The coordinator is still working. If it succeeds, the card appears in "
    "this channel: no need to try again."
)
UNAVAILABLE = "The coordinator is not available right now. The chat still works; try again in a minute."
# A message to Cadence whose answer is late: said once, posted when it comes.
ASK_SLOW = "Cadence is taking longer than usual: its answer will appear here."
LATE_ANSWER_LIMIT = 50
# A late answer that has not come after this long: Cadence says it could not
# answer (every message to Cadence ends in an answer or an error).
LATE_ANSWER_SECONDS = 180


class CoordinatorBridge:
    def __init__(self, manager: "BotManager") -> None:
        self._manager = manager
        # request id -> future woken by the server's answer
        self._waiting: dict[str, asyncio.Future] = {}
        # (conversation id, proposal id) -> the Discord message showing the card
        # there (this run only). Per channel: two Discord channels linked to the
        # same web space each show their own copy of a group's card.
        self._cards: dict[tuple[str, str], discord.Message] = {}
        # proposal id -> the last proposal seen, for "Why?" (this run only)
        self._proposals: dict[str, dict] = {}
        # Bot clients whose card buttons are registered (see _register_buttons).
        self._buttons_on: set[int] = set()
        # Messages to Cadence in the chat (chat()): follow-ups per channel, and
        # answers that came late: request id -> (channel, maybe).
        self._follow_ups = FollowUps()
        self._answers: set[asyncio.Task] = set()
        # Follow-ups also sent to Cadence's ask, until runtime.py marks their user_text.
        self._offered: set[str] = set()
        self._late: dict[str, tuple[Any, bool]] = {}

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

    async def chat(self, channel: Any, author_id: int, text: str, *, tagged: bool = False) -> bool:
        """
        A chat message in a linked channel that is for Cadence, or might be
        (addressing.for_cadence, the same rule as the web app): Cadence
        answers in the channel from everything the project holds (command
        "ask": who is writing, their tasks, the task they talk about). True
        when handled here; False sends it on as before (user_text). A
        follow-up is both: asked here in the background, and sent on, so the
        proactive judge still reads it (R10 on the server stops a second reply).
        While the answer is written Discord shows "Cadence is typing…".
        """
        found = self._manager.link_for_channel(getattr(channel, "id", 0) or 0)
        if found is None:
            return False
        bot, link = found
        place = f"discord:{link.text_channel_id}"
        routed = for_cadence(text, follow_ups=self._follow_ups, place=place,
                             member_names=bot.roster_text(link).values(), tagged=tagged, member=author_id)
        if routed is None:
            return False
        question, maybe, also_chat = routed
        if also_chat:
            # Asked in the background; the caller marks its user_text with
            # offered(text), so the server's R10 holds whichever arrives first.
            self._offered.add(text)
            task = asyncio.create_task(self._answer(channel, author_id, text, question, maybe, place))
            self._answers.add(task)
            task.add_done_callback(self._answers.discard)
            await asyncio.sleep(0)
            return False
        await self._answer(channel, author_id, text, question, maybe, place)
        return True

    def offered(self, text: str) -> bool:
        """True once for a message chat() also sent to Cadence's ask as a follow-up."""
        if text in self._offered:
            self._offered.discard(text)
            return True
        return False

    async def wait_for_answers(self) -> None:
        """Wait for the follow-ups being answered in the background (tests, shutdown)."""
        # Only the unfinished ones: awaiting finished tasks never yields, so the
        # done-callbacks that empty the set would never run (a busy loop).
        while pending := [t for t in self._answers if not t.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _answer(self, channel: Any, author_id: int, text: str, question: str, maybe: bool, place: str) -> None:
        request_id = uuid.uuid4().hex
        self._follow_ups.asked(place, author_id)  # only this member's next messages are follow-ups
        message = CoordinatorCommandMessage(
            event="coordinator_command", command="ask", member_id=author_id,
            args={"question": question, "said": text, **({"maybe": True} if maybe else {})},
            channel="discord", request_id=request_id,
        )
        if maybe:  # it may end in silence: no "typing"
            answer = await self._send_to(channel.id, request_id, message, errors_as_notice=True)
        else:
            async with channel.typing():
                answer = await self._send_to(channel.id, request_id, message, errors_as_notice=True)
        if answer is None:  # timed out: still being answered
            self._late[request_id] = (channel, maybe)
            while len(self._late) > LATE_ANSWER_LIMIT:
                self._late.pop(next(iter(self._late)))
            if not maybe:
                await self._say(channel, ASK_SLOW, place)
            asyncio.get_running_loop().call_later(
                LATE_ANSWER_SECONDS, lambda: asyncio.ensure_future(self.give_up(request_id))
            )
            return
        if maybe and not answer.get("ok"):
            return
        await self._say(channel, answer.get("text") or ("" if maybe else UNAVAILABLE), place)

    async def give_up(self, request_id: str) -> None:
        """A late answer that never came: Cadence says so (nothing for a maybe)."""
        found = self._late.pop(request_id, None)
        if found is not None and not found[1]:
            channel = found[0]
            await self._say(channel, UNAVAILABLE, f"discord:{getattr(channel, 'id', '')}")

    async def _say(self, channel: Any, text: str, place: str) -> None:
        if not text:
            return
        try:
            # No mentions: Cadence's words never ping anyone.
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
            self._follow_ups.answered(place)
        except discord.HTTPException:
            logger.exception("Could not post Cadence's answer in %s", place)

    async def _send(self, interaction: discord.Interaction, request_id: str, message) -> dict | None:
        channel_id = interaction.channel_id or 0
        if self._manager.link_for_channel(channel_id) is None:
            problem = await self._serve(interaction)
            if problem:
                return {"event": "coordinator_notice", "ok": False, "text": problem}
        return await self._send_to(channel_id, request_id, message)

    async def _serve(self, interaction: discord.Interaction) -> str:
        """
        One step, as on Slack: a /coordinator command in a channel the bot
        does not serve yet makes it serve that text channel (the lab's link,
        with no voice and the server's default listening mode), so a member
        never has to know `/mulca link`. Returns "" when the channel is
        served now, else the sentence for the member. `/mulca link` stays
        for voice or another listening mode. The lab's study welcome
        (messages.INTRO_MESSAGE) is not posted: it is not Cadence's.
        """
        channel = getattr(interaction, "channel", None)
        guild_id = getattr(interaction, "guild_id", None)
        bots = getattr(self._manager, "bots", None)
        if channel is None or guild_id is None or not bots:
            return NOT_LINKED  # a DM, or no bot running
        bot = self._manager.primary
        link = Link(text_channel_id=channel.id, guild_id=guild_id, bot_id=bot.user_id)
        problems = bot.store.conflicts(link)
        if problems:
            return "Cadence cannot work in this channel: " + " ".join(problems)
        previous = bot.store.save(link, created_by=getattr(interaction.user, "id", None))
        await bot.apply_link(link, previous)
        logger.info("coordinator: now serving channel %s (first /coordinator command there)", channel.id)
        return ""

    async def invite(self, message: Any) -> bool:
        """
        A web space's invite link pasted in a channel (invites.py): the channel
        is served and linked to that space at once, and Cadence says so in the
        channel, so everyone sees it worked. True when the message was one.
        """
        code = invite_in(getattr(message, "content", "") or "")
        guild = getattr(message, "guild", None)
        if code is None or guild is None:
            return False
        channel = message.channel
        acting = SimpleNamespace(channel=channel, channel_id=channel.id, guild_id=guild.id, user=message.author)
        answer = await self.send_command(acting, "link", {"code": code})
        text = answer_text(answer)
        if answer and answer.get("ok"):
            text += "\n" + LINKED_NEXT
        await self._say(channel, text, f"discord:{channel.id}")
        return True

    async def serve_voice(self, interaction: discord.Interaction, voice: Any) -> str:
        """
        /coordinator voice: the group's voice call joins this channel's
        project. The bot joins the call when someone is in it; every spoken
        turn is transcribed by MUCA-Server, kept as Cadence's context, shown
        in the web space ("Discord voice") and can become a card here.
        "ambient": every turn is judged (the wake modes judge only after
        "MULCA start", so nothing said before would ever become a card). The
        lab's unsolicited strategies stay silent in the call (server R12);
        Cadence speaks only when addressed. Returns the sentence for the member.
        """
        channel = getattr(interaction, "channel", None)
        found = self._manager.link_for_channel(getattr(channel, "id", 0) or 0)
        if found is None:
            problem = await self._serve(interaction)
            if problem:
                return problem
            found = self._manager.link_for_channel(channel.id)
            if found is None:
                return NOT_LINKED
        bot, link = found
        updated = dataclasses.replace(link, voice_channel_id=voice.id, listening_mode="ambient")
        problems = bot.store.conflicts(updated)
        if problems:
            return "Cadence cannot listen to that call: " + " ".join(problems)
        previous = bot.store.save(updated, created_by=getattr(interaction.user, "id", None))
        await bot.apply_link(updated, previous)
        logger.info("coordinator: %s now listens to voice channel %s", link.conversation_id, voice.id)
        return (
            f"Cadence now listens to {getattr(voice, 'mention', 'the voice call')}: it joins when someone is there. "
            "What is said is transcribed and saved in the project (also on the web, as “Discord voice”); "
            "a decision or a task said aloud becomes a card to confirm here. "
            "`/coordinator transcript` shows the last hour. Cadence speaks only if you call it by name."
        )

    async def _send_to(self, channel_id: int, request_id: str, message, *, errors_as_notice: bool = False) -> dict | None:
        """
        The server's answer; None when it did not come in time. A failure is
        None too for commands and clicks (they say NO_ANSWER), but an
        "unavailable" notice with `errors_as_notice`: a chat message must not
        be told "the answer will appear here" when the server is down.
        """
        found = self._manager.link_for_channel(channel_id)
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
            return {"event": "coordinator_notice", "ok": False, "text": UNAVAILABLE} if errors_as_notice else None
        finally:
            self._waiting.pop(request_id, None)

    async def warm_up(self, bot) -> int:
        """
        Open the session of each channel this bot serves, once it is ready.

        The server sends a card to the sessions of a linked group that are
        open *now* (LiveGroups): without this, after a restart a Discord
        channel heard nothing until someone wrote in it, so a card made on
        the web or on Slack never showed here. Only the roster is sent: no
        message, no model call of ours. A paused bot opens nothing. Returns
        how many sessions were opened; a channel that fails is logged and skipped.
        """
        if getattr(bot, "paused", False):
            return 0
        self._register_buttons(bot.client)
        opened = 0
        for link in bot.links():
            channel = bot.client.get_channel(link.text_channel_id)
            if channel is None:
                continue

            async def action(client, link=link) -> None:
                await client.send_participants(bot.roster_text(link), modality="text")

            try:
                await bot.registry.run(scope_for(bot, link), action, reply_channel=channel, retry_once=False)
                opened += 1
            except Exception:
                logger.exception("Could not open the session of %s", link.conversation_id)
        return opened

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
        elif event == "coordinator_notice" and data.get("requestId", "") in self._late:
            channel, maybe = self._late.pop(data["requestId"])
            if data.get("ok") or not maybe:
                await self._say(channel, str(data.get("text", "")), f"discord:{getattr(channel, 'id', '')}")
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
        key = (getattr(getattr(session, "scope", None), "conversation_id", ""), proposal_id)
        existing = self._cards.get(key)
        try:
            if existing is not None:
                await existing.edit(embed=embed, view=view)
                return
            channel = session.replies.channel
            if channel is None or proposal.get("status") != "pending":
                return  # nothing to show where no card was ever posted
            self._cards[key] = await channel.send(
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
