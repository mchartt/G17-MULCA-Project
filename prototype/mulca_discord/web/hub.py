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

A group's conversation id is "web:<invite code>": a web space is its own MUCA
conversation. A Discord or Slack channel can be *linked* to it with the invite
code (/coordinator link): then the project is shared, cards reach every
channel, and what is written there arrives here as "coordinator_mirror" and
is shown in the chat with the channel's name.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import date, timedelta
from typing import Any, Protocol

from muca_server.protocol import CoordinatorCommandMessage, ProposalResponseMessage

from ..addressing import MAX_QUESTION_CHARS as MAX_ADDRESSED_CHARS
from ..addressing import FollowUps, addressed, call
from ..courses import DEFAULT_COURSE
from ..muca_client import MucaConnectionLost
from ..sessions import Scope, ScopeSession, SessionRegistry
from .accounts import Accounts, User
from .calendar import CalendarFeeds
from .server_data import delete_conversation
from .store import Group, Member, WebStore

logger = logging.getLogger(__name__)

AGENT_NAME = "Cadence"
ANSWER_TIMEOUT_SECONDS = 60
MAX_MESSAGE_CHARS = 4000
# How the web app calls the agent ("@coordinator", or its product name
# "@Cadence"). MUCA-Server's respond_when_addressed strategy and persona know
# the agent as "MULCA", so the mention is forwarded under that name: the
# group's text and the chat history keep what the member wrote.
WEB_MENTION = re.compile(r"@(coordinator|cadence)\b", re.IGNORECASE)
SERVER_NAME_MENTION = "@MULCA"
# A message that calls Cadence ("@cadence", "Cadence, ...", "... right,
# cadence?", see addressing.py) is answered by the coordinator from
# everything the project holds (command "ask"), not by the lab's agent, which
# cannot read the plan. For a short while after Cadence answered, the next
# messages are offered to it as "maybe" (and only to it): it answers a
# follow-up and stays silent when the members talk among themselves. Only
# routing: no state change.
MAX_QUESTION_CHARS = MAX_ADDRESSED_CHARS

# CS6 wake-up (wake_due_groups): the server's progress timer runs only in an
# open session, and a group nobody opened since this adapter started has none.
# Every WAKE_EVERY_SECONDS the hub asks for one progress assessment, only for
# groups whose last saved plan has an open, owned task due from yesterday to
# the day after tomorrow (the server decides precisely, with its time zone).
WAKE_EVERY_SECONDS = 30 * 60
WAKE_FIRST_SECONDS = 2 * 60

UNAVAILABLE = "The coordinator is not available right now. The chat still works; try the command again in a minute."
NO_ANSWER = "The coordinator is still working. If it succeeds, the card appears in the chat: no need to try again."
# A message to Cadence whose answer is late: the "thinking" banner stays on and
# the answer is still posted when it comes (20/11: a late answer was dropped
# with its request). If none comes within LATE_ANSWER_SECONDS more, Cadence
# says it could not answer: every direct message ends in an answer or an error.
LATE_ANSWER_SECONDS = 180
LATE_ANSWER_LIMIT = 50


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


class SpaceFull(Exception):
    """The space already has as many members as a group may have."""


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
        # Not a follow-up window here: an unasked message (the plan opener's
        # question, a CS6 progress question) is answered in the normal chat, so
        # the reply goes on as user_text and the server routes it (the opener
        # hears it; MUCA-Server reads a reply to a progress question however late).
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
        max_members: int = 8,
    ) -> None:
        self.store = store
        # A group of students, not a community: a space stops accepting new
        # members here (MULCA_WEB_MAX_MEMBERS). Members already in stay in.
        self.max_members = max(1, max_members)
        # MUCA_ADMIN_TOKEN, to delete a group's data on MUCA-Server (server_data.py).
        self._admin_token = admin_token
        self.registry = registry or SessionRegistry(muca_url)
        # Instance attribute: shadows the class-level Discord hook for this registry only.
        self.registry.on_coordinator_event = self._on_coordinator_event
        self._course = course
        # Register / log in / profile (accounts.py), in the same database file.
        self.accounts = Accounts(store.connection)
        # M5: the calendar feed reads the last state saved here.
        self.calendar = CalendarFeeds(store)
        self._sockets: dict[int, set[Socket]] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._channels: dict[int, WebChannel] = {}
        self._waiting: dict[str, asyncio.Future] = {}
        self.follow_ups = FollowUps()
        # Messages to Cadence whose answer came after ANSWER_TIMEOUT_SECONDS:
        # request id -> (group id, maybe). Posted when the answer arrives.
        self._late: dict[str, tuple[int, bool]] = {}
        # Messages to Cadence being answered, per group: the "thinking" line.
        self._thinking: dict[int, int] = {}
        # Answers being written (post_message); the server answers them in order.
        self._answers: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # Groups and members
    # ------------------------------------------------------------------

    def create_group(self, name: str, display_name: str, user: User | None = None) -> tuple[Group, Member, str]:
        """A new space. With `user` (a logged-in person) the member is theirs."""
        group = self.store.create_group(_clean(name, 80) or "Our project")
        member, token = self._add_member(group, display_name, user)
        return group, member, token

    async def join_group(
        self, invite_code: str, display_name: str, user: User | None = None
    ) -> tuple[Group, Member, str] | None:
        group = self.store.group_by_code(invite_code)
        if group is None:
            return None
        # A logged-in person who is already a member gets back in as themselves
        # (a second browser), not as a second member with the same name.
        known = self.accounts.member_in(user.id, group.id) if user else None
        if known is not None:
            return group, self.store.member(known), self.accounts.new_access(known)
        if len(self.store.members(group.id)) >= self.max_members:
            raise SpaceFull(f"This space is full: a group has at most {self.max_members} members.")
        member, token = self._add_member(group, display_name, user)
        await self._announce_members(group.id)
        return group, member, token

    def _add_member(self, group: Group, display_name: str, user: User | None) -> tuple[Member, str]:
        name = user.display_name if user else _clean(display_name, 40)
        member, token = self.store.add_member(group.id, name)
        if user is not None:
            self.accounts.claim_member(member.id, user.id)
            # Their profile (discipline, skills, hours) goes to the coordinator.
            asyncio.create_task(self.share_profile(user, only_member=member.id))
        return member, token

    async def share_profile(self, user: User, *, only_member: int | None = None) -> None:
        """
        Send the person's profile to the coordinator of their spaces, so they
        fill it in once and every group sees it. Best effort: if MUCA-Server
        is off, the account still has the profile and the next save sends it.
        """
        for member_id, group_id in self.accounts.member_ids(user.id):
            if only_member is not None and member_id != only_member:
                continue
            member = self.store.member(member_id)
            if member is None:
                continue
            try:
                await self.command(member, "profile", user.profile_args())
                await self._announce_members(group_id)
            except Exception:
                logger.exception("Could not share the profile of member %s", member_id)

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
        # Open the group's session now, not at the first message: a linked
        # channel's messages and cards only reach an open session.
        asyncio.create_task(self._warm_up(member.group_id))

    async def _warm_up(self, group_id: int) -> None:
        async def action(client) -> None:
            await client.send_participants(self.roster(group_id), modality="text")

        try:
            await self._run(group_id, action)
        except Exception:  # MUCA-Server down: the chat still opens
            logger.info("Could not open the session of web group %s yet", group_id)

    async def _hello(self, socket: Socket, member: Member) -> None:
        group = self.store.group(member.group_id)
        await socket.send_json(
            {
                "type": "hello",
                "agentName": AGENT_NAME,
                "group": {"id": group.id, "name": group.name, "inviteCode": group.invite_code},
                "me": {"id": member.id, "name": member.display_name},
                # Cadence is answering right now (a tab opened or reconnected mid-answer).
                "thinking": self._thinking.get(group.id, 0) > 0,
                "members": self._members_json(group.id),
                "messages": [self.message_json(m) for m in self.store.history(group.id)],
            }
        )
        # The cards still waiting for a click, after the history: a reload or a
        # member who joins later must still be able to answer them.
        for proposal in self.store.open_proposals(group.id):
            await socket.send_json({"type": "proposal", "proposal": proposal})

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

        # Answers run in the background (the socket reads the member's next
        # message at once, so "Cadence, mi senti?" typed under the banner is
        # shown, not held for up to 60 s); the server answers them in order.
        offered = False  # also sent to Cadence's ask as a possible follow-up
        called = call(text)
        if called and called[1]:
            self._answer_later(member, called[0], said=text)
            return
        if called:
            # Names Cadence without the shape of a call ("Cadence ieri ha risposto
            # male", "secondo me Cadence è inutile"): maybe talking about it.
            # Offered whole as "maybe" (it may stay silent). Like a sure call, not
            # sent on as user_text: the name would let the lab's
            # respond_when_addressed answer it a second time (7.6).
            self._answer_later(member, text[:MAX_QUESTION_CHARS], maybe=True, said=text)
            return
        if self.follow_ups.is_follow_up(str(member.group_id), text, self.roster(member.group_id).values()):
            # Maybe for Cadence: offered to it (it may stay silent), and ALSO sent on
            # as user_text below. Without it the plan opener never heard its answers
            # and CS3/CS7 never saw these lines (a pending card opens this window).
            # The double reply seen on 20/11 (the lab's agent answering too) is
            # stopped on the server: R10. The user_text below says it was
            # offered (offered_to_ask), so the server knows whichever of the
            # two arrives first (the ask runs in the background: on 21/11 the
            # message still got a second answer, and once two cards).
            self._answer_later(member, text[:MAX_QUESTION_CHARS], maybe=True, said=text)
            offered = True

        async def action(client) -> None:
            await client.send_participants(self.roster(member.group_id), modality="text")
            await client.send_user_text(
                speaker=member.id,
                speaker_name=member.display_name,
                text=WEB_MENTION.sub(SERVER_NAME_MENTION, text),
                mentions_assistant=WEB_MENTION.search(text) is not None,
                offered_to_ask=offered,
            )

        try:
            await self._run(member.group_id, action)
        except (ConnectionError, OSError):
            logger.exception("MUCA-Server unreachable; message kept in the web chat only")
            await self.broadcast(member.group_id, {"type": "status", "coordinator": "unavailable"})

    async def wait_for_answers(self) -> None:
        """Wait until every answer started by post_message is posted (tests, shutdown)."""
        # Only the unfinished ones: awaiting finished tasks never yields, so the
        # done-callbacks that empty the set would never run (a busy loop).
        while pending := [t for t in self._answers if not t.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    def _answer_later(self, member: Member, question: str, *, maybe: bool = False, said: str = "") -> None:
        task = asyncio.create_task(self._answer_safely(member, question, maybe=maybe, said=said))
        self._answers.add(task)
        task.add_done_callback(self._answers.discard)

    async def _answer_safely(self, member: Member, question: str, *, maybe: bool, said: str) -> None:
        try:
            await self._answer_in_chat(member, question, maybe=maybe, said=said)
        except Exception:
            logger.exception("Cadence's answer failed for group %s", member.group_id)
            if not maybe:
                await self._say(member.group_id, UNAVAILABLE)

    async def _answer_in_chat(self, member: Member, question: str, *, maybe: bool = False, said: str = "") -> None:
        """
        Cadence's answer, posted in the chat for the whole group; a "maybe" left
        unanswered posts nothing. A sure call shows "Cadence is thinking…" to
        everyone until its answer is in the chat, or the failure is said; so does a
        "maybe" too (a follow-up without the name): its answer took 10-30 s
        with no sign at all and the group thought Cadence was not answering
        (Matteo, 21/11); a thinking line that ends in silence is the lesser evil.
        """
        args = {"question": question, "said": said or question, **({"maybe": True} if maybe else {})}
        request_id = uuid.uuid4().hex
        group_id = member.group_id
        await self._think(group_id, +1)
        late = False
        try:
            try:
                answer = await self.command(member, "ask", args, request_id=request_id)
            except Exception:
                if maybe:
                    logger.exception("follow-up offered to Cadence failed")
                    return
                raise
            late = bool(answer.get("late"))
            if late:
                # Still being answered: posted when it comes (_on_coordinator_event).
                self._late[request_id] = (group_id, maybe)
                while len(self._late) > LATE_ANSWER_LIMIT:
                    await self._give_up(next(iter(self._late)))
                asyncio.get_running_loop().call_later(
                    LATE_ANSWER_SECONDS, lambda: asyncio.ensure_future(self._give_up(request_id))
                )
                return
            if maybe and answer.get("ok") is False:
                return  # never shown for a message not sent to Cadence
            await self._say(group_id, answer.get("text") or ("" if maybe else UNAVAILABLE))
        finally:
            # Off once the answer is in the chat (or the failure said), not before.
            if not late:
                await self._think(group_id, -1)

    async def _think(self, group_id: int, step: int) -> None:
        """Count the answers being written; tell the group when it starts and stops."""
        before = self._thinking.get(group_id, 0)
        now = max(0, before + step)
        self._thinking[group_id] = now
        if (before == 0) != (now == 0):
            await self.broadcast(group_id, {"type": "typing", "on": now > 0})
        elif step < 0 and now > 0:
            # Cadence's message just cleared the line in the browser, and another
            # answer is still on its way: show it again.
            await self.broadcast(group_id, {"type": "typing", "on": True})

    async def _give_up(self, request_id: str) -> None:
        """A late answer that never came: the banner goes off and Cadence says so."""
        found = self._late.pop(request_id, None)
        if found is None:
            return
        group_id, maybe = found
        if not maybe:
            await self._say(group_id, UNAVAILABLE)
        await self._think(group_id, -1)

    async def _say(self, group_id: int, text: str) -> None:
        """Cadence speaks in the group's chat (nothing for an empty text)."""
        if not text:
            return
        channel = self._channels.setdefault(group_id, WebChannel(self, self.store.group(group_id)))
        await channel.send(text)
        self.follow_ups.answered(str(group_id))

    def groups_with_close_deadlines(self, today: date | None = None) -> list[int]:
        """Groups whose saved plan has an open task with an owner due between yesterday and in two days."""
        today = today or date.today()
        lo, hi = today - timedelta(days=1), today + timedelta(days=2)
        found = []
        for group_id, state in self.calendar.states():
            for task in state.get("tasks") or []:
                try:
                    due = date.fromisoformat(str(task.get("due_date") or ""))
                except ValueError:
                    continue
                if task.get("status") != "done" and task.get("owner_id") and lo <= due <= hi:
                    found.append(group_id)
                    break
        return found

    async def wake_due_groups(self, today: date | None = None) -> int:
        """Ask MUCA-Server for one CS6 assessment in each such group (it may well stay silent)."""
        woken = 0
        for group_id in self.groups_with_close_deadlines(today):
            members = self.store.members(group_id)
            if not members:
                continue
            try:
                await self.command(members[0], "progress")
                woken += 1
            except Exception:  # one group's failure must not stop the others
                logger.exception("progress wake-up failed for group %s", group_id)
        return woken

    async def wake_loop(self) -> None:
        await asyncio.sleep(WAKE_FIRST_SECONDS)
        while True:
            try:
                await self.wake_due_groups()
            except Exception:
                logger.exception("progress wake-up round failed")
            await asyncio.sleep(WAKE_EVERY_SECONDS)

    async def rename_group(self, member: Member, name: str) -> dict:
        """Project settings: a new name for the space; every open tab of the group shows it."""
        group = self.store.rename_group(member.group_id, name)
        frame = {"id": group.id, "name": group.name, "inviteCode": group.invite_code}
        await self.broadcast(group.id, {"type": "group", "group": frame})
        return frame

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

    async def command(
        self, member: Member, command: str, args: dict | None = None, *, request_id: str | None = None
    ) -> dict:
        request_id = request_id or uuid.uuid4().hex
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
            return {"type": "notice", "ok": False, "text": NO_ANSWER, "late": True}
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
        data = browser_safe(data)
        if event == "coordinator_proposal":
            proposal = data.get("proposal", {})
            self.store.save_proposal(group.id, proposal)
            await self.broadcast(group.id, {"type": "proposal", "proposal": proposal})
            if proposal.get("status") == "pending":
                # A new card is Cadence speaking too: "Sì, fallo" typed under it is
                # offered to Cadence as maybe (it points to the card; the click saves).
                self.follow_ups.answered(str(group.id))
        elif event == "coordinator_state":
            # The panel of every member follows the state, whoever asked for it.
            self.calendar.save_state(group.id, data.get("state", {}))
            await self.broadcast(group.id, {"type": "state", "state": data.get("state", {})})
        elif event == "coordinator_mirror":
            await self._show_mirror(group.id, data)
        future = self._waiting.get(data.get("requestId", ""))
        if future is not None and not future.done():
            future.set_result(_answer(data))
        elif event == "coordinator_notice" and data.get("requestId", "") in self._late:
            _, maybe = self._late.pop(data["requestId"])
            if data.get("ok") or not maybe:
                await self._say(group.id, str(data.get("text", "")))
            await self._think(group.id, -1)

    async def _show_mirror(self, group_id: int, data: dict) -> None:
        """A message written on Discord or Slack: kept in the history, shown to everyone."""
        text = str(data.get("text", ""))[:MAX_MESSAGE_CHARS]
        if not text:
            return
        stored = self.store.add_message(
            group_id,
            None,
            text,
            channel=str(data.get("channel", "discord"))[:20],
            author_name=_clean(str(data.get("speakerName", "")), 40) or "A member",
        )
        await self.broadcast(group_id, {"type": "message", "message": self.message_json(stored)})

    async def _announce_members(self, group_id: int) -> None:
        await self.broadcast(group_id, {"type": "members", "members": self._members_json(group_id)})

    def _members_json(self, group_id: int) -> list[dict]:
        return [{"id": m.id, "name": m.display_name} for m in self.store.members(group_id)]

    async def close(self) -> None:
        await self.registry.close_all()


# The largest whole number a browser reads exactly (JavaScript's Number).
BROWSER_MAX_INT = 2**53 - 1


def browser_safe(value):
    """
    In a linked group a card can name a Discord or Slack member, whose id is
    larger than a browser can read exactly (it would be rounded, and no name
    would match). Those ids travel as text; web members' ids stay numbers.
    """
    if isinstance(value, dict):
        return {key: browser_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [browser_safe(item) for item in value]
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > BROWSER_MAX_INT:
        return str(value)
    return value


def _answer(data: dict) -> dict:
    if data.get("event") == "coordinator_state":
        return {"type": "state", "state": data.get("state", {}), "ok": True}
    answer = {"type": "notice", "ok": bool(data.get("ok")), "text": data.get("text", "")}
    if data.get("catchup") is not None:
        answer["catchup"] = data["catchup"]  # the "catchup" command's payload
    if data.get("reflection") is not None:
        answer["reflection"] = data["reflection"]  # the "reflection" command's payload
    return answer


def typed_question(text: str) -> str:
    """ "Cadence, who does the slides?" -> "who does the slides?"; "" when the message does not call Cadence."""
    return addressed(text) or ""


def _clean(text: str, limit: int) -> str:
    return " ".join((text or "").split())[:limit]
