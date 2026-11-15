"""
WebHub: the web app as one more channel of the MULCA process.

    browser --WebSocket--> app.py --> WebHub --> SessionRegistry (web's own) --> MUCA-Server
    browser <--WebSocket-- app.py <-- WebHub <-- coordinator events, streamed replies

What it reuses instead of rewriting (project rule: build on what exists):
  * SessionRegistry / MucaWsClient: one MUCA session per group, reopened when
    lost, exactly as Discord does;
  * ReplyDispatcher: the agent's streamed reply goes to a WebChannel, an object
    with the two methods a Discord text channel offers (send, then edit);
  * the coordinator protocol events (coordinator_command, proposal_response)
    with channel="web".

The coordinator hook is set on THIS registry instance, so Discord's hook (set on
the SessionRegistry class by coordinator/bridge.py) is untouched.

A group's conversation id is "web:<invite code>": web groups are their own MUCA
conversations. Joining a Discord group to the same conversation is the next
step of the multichannel plan (needs A5/A6 verified live), not done here.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any, Protocol

from muca_server.protocol import CoordinatorCommandMessage, ProposalResponseMessage

from ..courses import DEFAULT_COURSE
from ..muca_client import MucaConnectionLost
from ..sessions import Scope, ScopeSession, SessionRegistry
from .calendar import CalendarFeeds
from .server_data import delete_conversation
from .store import Group, Member, WebStore

logger = logging.getLogger(__name__)

AGENT_NAME = "Cadence"
ANSWER_TIMEOUT_SECONDS = 60
MAX_MESSAGE_CHARS = 4000
MENTION = "@coordinator"
# "@coordinator why ..." / "@coordinator perché ..." typed in the chat: answered
# from the decision log (command "why"), not by the lab's agent, which cannot
# read the log. Only routes a question: it never changes any state.
TYPED_WHY = re.compile(r"^\s*@coordinator\b[\s,:]*(?P<question>(why|perch[eé]|perche)\b.*)$", re.IGNORECASE | re.DOTALL)

UNAVAILABLE = "The coordinator is not available right now. The chat still works; try the command again in a minute."
NO_ANSWER = "The coordinator is still working. If it succeeds, the card appears in the chat: no need to try again."


class Socket(Protocol):
    async def send_json(self, data: Any) -> None: ...


class WebReply:
    """One agent reply as ReplyDispatcher sees a Discord message: .content and edit()."""

    def __init__(self, channel: "WebChannel", message_id: int, content: str) -> None:
        self._channel = channel
        self.id = message_id
        self.content = content

    async def edit(self, *, content: str) -> None:
        self.content = content
        await self._channel.update(self)


class WebChannel:
    """The group's chat as a reply target: every send/edit becomes a 'message' event."""

    def __init__(self, hub: "WebHub", group: Group) -> None:
        self._hub = hub
        self._group = group

    async def send(self, content: str | None = None, **_: Any) -> WebReply:
        text = content or ""
        stored = self._hub.store.add_message(self._group.id, None, text)
        reply = WebReply(self, stored.id, text)
        await self._hub.broadcast(self._group.id, {"type": "message", "message": self._hub.message_json(stored)})
        return reply

    async def update(self, reply: WebReply) -> None:
        stored = self._hub.store.update_message(reply.id, reply.content)
        await self._hub.broadcast(self._group.id, {"type": "message", "message": self._hub.message_json(stored)})


class WebHub:
    def __init__(
        self,
        store: WebStore,
        muca_url: str,
        *,
        registry: SessionRegistry | None = None,
        course: str = DEFAULT_COURSE,
        admin_token: str = "",
    ) -> None:
        self.store = store
        # MUCA_ADMIN_TOKEN, to delete a group's data on MUCA-Server (server_data.py).
        self._admin_token = admin_token
        self.registry = registry or SessionRegistry(muca_url)
        # Instance attribute: shadows the class-level Discord hook for this registry only.
        self.registry.on_coordinator_event = self._on_coordinator_event
        self._course = course
        # M5: the calendar feed reads the last state saved here.
        self.calendar = CalendarFeeds(store)
        self._sockets: dict[int, set[Socket]] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._channels: dict[int, WebChannel] = {}
        self._waiting: dict[str, asyncio.Future] = {}

    # ------------------------------------------------------------------
    # Groups and members
    # ------------------------------------------------------------------

    def create_group(self, name: str, display_name: str) -> tuple[Group, Member, str]:
        group = self.store.create_group(_clean(name, 80) or "Our project")
        member, token = self.store.add_member(group.id, _clean(display_name, 40))
        return group, member, token

    async def join_group(self, invite_code: str, display_name: str) -> tuple[Group, Member, str] | None:
        group = self.store.group_by_code(invite_code)
        if group is None:
            return None
        member, token = self.store.add_member(group.id, _clean(display_name, 40))
        await self._announce_members(group.id)
        return group, member, token

    def roster(self, group_id: int) -> dict[int, str]:
        return {m.id: m.display_name for m in self.store.members(group_id)}

    def message_json(self, message) -> dict:
        return message.to_json(self.roster(message.group_id))

    # ------------------------------------------------------------------
    # Sockets
    # ------------------------------------------------------------------

    def _lock(self, group_id: int) -> asyncio.Lock:
        """
        One lock per group around "join the broadcast list + hello" and around
        each broadcast. Without it a broadcast (e.g. "Bruno joined") could be
        written to a new socket *before* its hello, and the older hello would
        then overwrite the newer member list (found by the M3 e2e tests).
        """
        return self._locks.setdefault(group_id, asyncio.Lock())

    async def connect(self, socket: Socket, member: Member) -> None:
        async with self._lock(member.group_id):
            self._sockets.setdefault(member.group_id, set()).add(socket)
            await self._hello(socket, member)

    async def _hello(self, socket: Socket, member: Member) -> None:
        group = self.store.group(member.group_id)
        await socket.send_json(
            {
                "type": "hello",
                "agentName": AGENT_NAME,
                "group": {"id": group.id, "name": group.name, "inviteCode": group.invite_code},
                "me": {"id": member.id, "name": member.display_name},
                "members": self._members_json(group.id),
                "messages": [self.message_json(m) for m in self.store.history(group.id)],
            }
        )

    def disconnect(self, socket: Socket, member: Member) -> None:
        self._sockets.get(member.group_id, set()).discard(socket)

    async def broadcast(self, group_id: int, data: dict) -> None:
        async with self._lock(group_id):
            for socket in list(self._sockets.get(group_id, ())):
                try:
                    await socket.send_json(data)
                except Exception:  # a closed tab must not stop the others
                    self._sockets[group_id].discard(socket)

    # ------------------------------------------------------------------
    # Going out: what a member does
    # ------------------------------------------------------------------

    async def post_message(self, member: Member, text: str) -> None:
        text = text.strip()[:MAX_MESSAGE_CHARS]
        if not text:
            return
        stored = self.store.add_message(member.group_id, member.id, text)
        await self.broadcast(member.group_id, {"type": "message", "message": self.message_json(stored)})

        typed_why = TYPED_WHY.match(text)
        if typed_why:
            await self._answer_typed_why(member, typed_why["question"].strip())
            return

        async def action(client) -> None:
            await client.send_participants(self.roster(member.group_id), modality="text")
            await client.send_user_text(
                speaker=member.id,
                speaker_name=member.display_name,
                text=text,
                mentions_assistant=MENTION in text.lower(),
            )

        try:
            await self._run(member.group_id, action)
        except (ConnectionError, OSError):
            logger.exception("MUCA-Server unreachable; message kept in the web chat only")
            await self.broadcast(member.group_id, {"type": "status", "coordinator": "unavailable"})

    async def _answer_typed_why(self, member: Member, question: str) -> None:
        """The answer from the decision log, posted in the chat for the whole group."""
        answer = await self.command(member, "why", {"question": question})
        channel = self._channels.setdefault(member.group_id, WebChannel(self, self.store.group(member.group_id)))
        await channel.send(answer.get("text") or UNAVAILABLE)

    async def delete_group(self, member: Member) -> bool:
        """
        Delete everything about the member's group: first on MUCA-Server (the
        session is closed, then its SQLite file removed), then the web side.
        If the server part fails, nothing is deleted, so the group can retry.
        """
        group = self.store.group(member.group_id)
        await self.registry.close(group.conversation_id, wait=5)
        if not await delete_conversation(self.registry.url, self._admin_token, group.conversation_id):
            return False
        await self.broadcast(group.id, {"type": "deleted"})
        for socket in list(self._sockets.pop(group.id, ())):
            close = getattr(socket, "close", None)
            if close is not None:
                try:
                    await close(code=4410)
                except Exception:  # already closed
                    pass
        self._channels.pop(group.id, None)
        self.store.delete_group(group.id)
        return True

    async def command(self, member: Member, command: str, args: dict | None = None) -> dict:
        request_id = uuid.uuid4().hex
        return await self._ask(
            member,
            request_id,
            CoordinatorCommandMessage(
                event="coordinator_command",
                command=command,
                member_id=member.id,
                args=args or {},
                channel="web",
                request_id=request_id,
            ),
        )

    async def click(self, member: Member, proposal_id: str, action: str, *, option: int | None = None) -> dict:
        request_id = uuid.uuid4().hex
        return await self._ask(
            member,
            request_id,
            ProposalResponseMessage(
                event="proposal_response",
                proposal_id=proposal_id,
                action=action,
                option=option,
                member_id=member.id,
                channel="web",
                request_id=request_id,
            ),
        )

    async def _ask(self, member: Member, request_id: str, message) -> dict:
        future = asyncio.get_running_loop().create_future()
        self._waiting[request_id] = future

        async def action(client) -> None:
            # The server checks members against this roster: send it first.
            await client.send_participants(self.roster(member.group_id), modality="text")
            await client.send_coordinator(message)

        try:
            await self._run(member.group_id, action)
            return await asyncio.wait_for(future, ANSWER_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return {"type": "notice", "ok": False, "text": NO_ANSWER}
        except (ConnectionError, OSError, MucaConnectionLost):
            logger.exception("Coordinator %s failed for group %s", message.event, member.group_id)
            return {"type": "notice", "ok": False, "text": UNAVAILABLE}
        finally:
            self._waiting.pop(request_id, None)

    async def _run(self, group_id: int, action) -> ScopeSession:
        group = self.store.group(group_id)
        channel = self._channels.setdefault(group_id, WebChannel(self, group))
        return await self.registry.run(
            Scope(
                conversation_id=group.conversation_id,
                bot_name=AGENT_NAME,
                channel_name=f"web-{group.id}",
                course=self._course,
            ),
            action,
            reply_channel=channel,
            retry_once=False,  # a message or a command must never run twice
        )

    # ------------------------------------------------------------------
    # Coming back: MUCA-Server's coordinator events
    # ------------------------------------------------------------------

    async def _on_coordinator_event(self, session: ScopeSession, data: dict) -> None:
        group = self.store.group_by_code(session.scope.conversation_id.removeprefix("web:"))
        if group is None:
            return
        event = data.get("event")
        if event == "coordinator_proposal":
            await self.broadcast(group.id, {"type": "proposal", "proposal": data.get("proposal", {})})
        elif event == "coordinator_state":
            # The panel of every member follows the state, whoever asked for it.
            self.calendar.save_state(group.id, data.get("state", {}))
            await self.broadcast(group.id, {"type": "state", "state": data.get("state", {})})
        future = self._waiting.get(data.get("requestId", ""))
        if future is not None and not future.done():
            future.set_result(_answer(data))

    async def _announce_members(self, group_id: int) -> None:
        await self.broadcast(group_id, {"type": "members", "members": self._members_json(group_id)})

    def _members_json(self, group_id: int) -> list[dict]:
        return [{"id": m.id, "name": m.display_name} for m in self.store.members(group_id)]

    async def close(self) -> None:
        await self.registry.close_all()


def _answer(data: dict) -> dict:
    if data.get("event") == "coordinator_state":
        return {"type": "state", "state": data.get("state", {}), "ok": True}
    return {"type": "notice", "ok": bool(data.get("ok")), "text": data.get("text", "")}


def _clean(text: str, limit: int) -> str:
    return " ".join((text or "").split())[:limit]
