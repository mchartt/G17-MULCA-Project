"""
SlackHub: the Slack side of the Group Coordinator, between Slack and
MUCA-Server. The Slack twin of web/hub.py and coordinator/bridge.py.

A Slack channel the bot was invited to is one MUCA conversation,
"slack:<channel id>". It can be linked to a web space with
/coordinator link <invite code>, like a Discord channel.

Going out (a member acts):
    on_message   a message in the channel -> user_text (the agent may answer)
    on_command   /coordinator ...         -> coordinator_command
    on_action    a card button            -> proposal_response
Coming back (MUCA-Server answers), _on_coordinator_event:
    coordinator_proposal -> the card is posted in the channel, or updated
    coordinator_mirror   -> a message written in a linked channel, as one line
    notice / state with a request id -> the private answer to a command or click

How Slack delivers events (Socket Mode) is in __main__.py; here there is no
Slack SDK at all, only the small SlackApi interface (api.py).
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid

from muca_server.protocol import CoordinatorCommandMessage, ProposalResponseMessage

from ..coordinator.card_content import why_text
from ..coordinator.cards import split_action
from ..coordinator.texts import catchup_text, mirror_text
from ..courses import DEFAULT_COURSE
from ..muca_client import MucaConnectionLost
from ..sessions import Scope, ScopeSession, SessionRegistry
from . import ids
from .api import SlackApi
from .cards import ACTION_ID, card_blocks, card_text, to_mrkdwn
from .commands import Usage, parse, state_text

logger = logging.getLogger(__name__)

AGENT_NAME = "Cadence"
PREFIX = "slack:"
ANSWER_TIMEOUT_SECONDS = 60
MENTION = "@coordinator"
USER_MENTION = re.compile(r"<@([A-Z0-9]+)>")
CHANNEL_ONLY = "The coordinator works in a channel, not in a direct message. Invite it to your group's channel."
UNAVAILABLE = "The coordinator is not available right now. Try again in a minute."
NO_ANSWER = "The coordinator is still working. If it succeeds, the card appears in this channel: no need to try again."


class SlackReply:
    """One agent reply as ReplyDispatcher sees a Discord message: .content and edit()."""

    def __init__(self, channel: "SlackChannel", ts: str, content: str) -> None:
        self._channel = channel
        self.ts = ts
        self.content = content

    async def edit(self, *, content: str) -> None:
        self.content = content
        await self._channel.api.update(self._channel.id, self.ts, to_mrkdwn(content))


class SlackChannel:
    """A Slack channel as a reply target (what a Discord channel is for dispatch.py)."""

    def __init__(self, api: SlackApi, channel_id: str) -> None:
        self.api = api
        self.id = channel_id

    async def send(self, content: str | None = None, **_) -> SlackReply:
        text = content or ""
        return SlackReply(self, await self.api.post(self.id, to_mrkdwn(text)), text)


class SlackHub:
    def __init__(
        self,
        api: SlackApi,
        muca_url: str,
        *,
        registry: SessionRegistry | None = None,
        course: str = DEFAULT_COURSE,
    ) -> None:
        self._api = api
        self.registry = registry or SessionRegistry(muca_url)
        # Instance attribute: this registry's events come here, not to Discord's bridge.
        self.registry.on_coordinator_event = self._on_coordinator_event
        self._course = course
        self._channels: dict[str, SlackChannel] = {}
        self._waiting: dict[str, asyncio.Future] = {}
        # proposal id -> timestamp of the Slack message showing its card
        self._cards: dict[str, str] = {}
        # proposal id -> the last proposal seen, for "Why?" (this run only)
        self._proposals: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Going out
    # ------------------------------------------------------------------

    async def on_message(self, event: dict) -> None:
        """A Slack "message" event. Only plain messages written by people in a channel."""
        if event.get("subtype") or event.get("bot_id") or event.get("channel_type") == "im":
            return  # edits, joins, bots (also our own posts), direct messages
        channel, user = event.get("channel", ""), event.get("user", "")
        text = (event.get("text") or "").strip()
        if not channel or not user or user == self._api.bot_user or not text:
            return
        roster = await self._api.roster(channel)
        mentions_bot = f"<@{self._api.bot_user}>" in text or MENTION in text.lower()
        # "<@U123>" means nothing to the model: write the person's name.
        readable = USER_MENTION.sub(
            lambda m: MENTION if m[1] == self._api.bot_user else f"@{roster.get(m[1], 'someone')}", text
        )

        async def action(client) -> None:
            await client.send_participants(_participants(roster), modality="text")
            await client.send_user_text(
                speaker=ids.member_id(user),
                speaker_name=roster.get(user, "member"),
                text=readable,
                mentions_assistant=mentions_bot,
            )

        try:
            await self._run(channel, action)
        except (ConnectionError, OSError, MucaConnectionLost):
            logger.exception("MUCA-Server unreachable; Slack message not delivered")

    async def on_command(self, channel: str, user: str, text: str, *, is_dm: bool = False) -> str:
        """/coordinator <text>: runs it and returns the private answer for the member."""
        if is_dm:
            return CHANNEL_ONLY
        try:
            command, args = parse(text)
        except Usage as usage:
            return str(usage)
        answer = await self._ask(channel, user, lambda request_id: CoordinatorCommandMessage(
            event="coordinator_command",
            command=command,
            member_id=ids.member_id(user),
            args=args,
            channel="slack",
            request_id=request_id,
        ))
        if command == "catchup":
            return to_mrkdwn(catchup_text(answer))
        if answer and answer.get("event") == "coordinator_state":
            return state_text(answer.get("state", {}))
        return _answer_text(answer)

    async def on_action(self, channel: str, user: str, action_id: str, message_ts: str = "") -> str:
        """A card button: returns the private answer for the member who clicked."""
        match = ACTION_ID.match(action_id)
        if match is None:
            return "This button is not known to the coordinator."
        proposal_id = match["proposal_id"]
        if message_ts:
            # Also after a restart: now we know which message shows this card.
            self._cards.setdefault(proposal_id, message_ts)
        if match["action"] == "why":
            return await self._why(channel, user, proposal_id)
        action, option = split_action(match["action"])
        answer = await self._ask(channel, user, lambda request_id: ProposalResponseMessage(
            event="proposal_response",
            proposal_id=proposal_id,
            action=action,
            option=option,
            member_id=ids.member_id(user),
            channel="slack",
            request_id=request_id,
        ))
        return _answer_text(answer)

    async def _why(self, channel: str, user: str, proposal_id: str) -> str:
        """The strategy and the messages behind the card; asked to the server after a restart."""
        proposal = self._proposals.get(proposal_id)
        if proposal is None:
            answer = await self._ask(channel, user, lambda request_id: CoordinatorCommandMessage(
                event="coordinator_command",
                command="card",
                member_id=ids.member_id(user),
                args={"proposal_id": proposal_id},
                channel="slack",
                request_id=request_id,
            ))
            proposal = (answer or {}).get("proposal")
            if proposal is None:
                return _answer_text(answer)
            self._proposals[proposal_id] = proposal
        return to_mrkdwn(why_text(proposal))

    async def _ask(self, channel: str, user: str, build) -> dict | None:
        """Send one coordinator message and wait for the answer with its request id."""
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._waiting[request_id] = future
        message = build(request_id)

        async def action(client) -> None:
            # The server checks members against this roster: send it first.
            await client.send_participants(_participants(await self._api.roster(channel)), modality="text")
            await client.send_coordinator(message)

        try:
            await self._run(channel, action)
            return await asyncio.wait_for(future, ANSWER_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return None
        except Exception:
            logger.exception("Coordinator %s failed for Slack channel %s", message.event, channel)
            return {"event": "coordinator_notice", "ok": False, "text": UNAVAILABLE}
        finally:
            self._waiting.pop(request_id, None)

    async def _run(self, channel: str, action) -> ScopeSession:
        target = self._channels.setdefault(channel, SlackChannel(self._api, channel))
        return await self.registry.run(
            Scope(conversation_id=PREFIX + channel, bot_name=AGENT_NAME, channel_name=f"slack-{channel}", course=self._course),
            action,
            reply_channel=target,
            retry_once=False,  # a message or a command must never run twice
        )

    # ------------------------------------------------------------------
    # Coming back
    # ------------------------------------------------------------------

    async def _on_coordinator_event(self, session: ScopeSession, data: dict) -> None:
        channel = session.scope.conversation_id.removeprefix(PREFIX)
        event = data.get("event")
        try:
            if event == "coordinator_proposal":
                await self._show_card(channel, data.get("proposal", {}))
                return
            if event == "coordinator_mirror":
                await self._api.post(channel, to_mrkdwn(mirror_text(data)))
                return
        except Exception:  # Slack refused: the session must keep working
            logger.exception("Could not show %s in Slack channel %s", event, channel)
            return
        future = self._waiting.get(data.get("requestId", ""))
        if future is not None and not future.done():
            future.set_result(data)

    async def _show_card(self, channel: str, proposal: dict) -> None:
        """Update the card if we know its message; otherwise post it while it is pending."""
        proposal_id = proposal.get("proposal_id", "")
        self._proposals[proposal_id] = proposal
        ts = self._cards.get(proposal_id)
        if ts is not None:
            await self._api.update(channel, ts, card_text(proposal), card_blocks(proposal))
        elif proposal.get("status") == "pending":
            self._cards[proposal_id] = await self._api.post(channel, card_text(proposal), card_blocks(proposal))

    async def close(self) -> None:
        await self.registry.close_all()


def _participants(roster: dict[str, str]) -> dict[int, str]:
    return {ids.member_id(user): name for user, name in roster.items()}


def _answer_text(answer: dict | None) -> str:
    """What to tell the member: the server's notice, or that it did not answer."""
    if answer is None:
        return NO_ANSWER
    if answer.get("event") == "coordinator_notice":
        return to_mrkdwn(answer.get("text") or ("Done." if answer.get("ok") else "Not done."))
    return "Done."
