"""
The MUCA-Server sessions this bot holds open, one per conversation scope.

A scope is an instance ("instance:<name>", shared by its text and voice
channels, so they share one memory) or a DM ("dm:<user_id>"). Sessions are
opened lazily, and reopened when MUCA-Server goes away (a restart, a network
blip): the next use of a lost scope connects again, replaying the handshake,
and the server restores the conversation's memory from its own store.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from websockets.exceptions import WebSocketException

from .dispatch import ReplyDispatcher
from .muca_client import MucaConnectionLost, MucaWsClient

logger = logging.getLogger(__name__)

ClientFactory = Callable[..., MucaWsClient]
StateUpdateHandler = Callable[[dict], Awaitable[None]]

# Waits between attempts to (re)open a session.
RECONNECT_DELAYS_SECONDS = (0.0, 0.5, 1.0, 2.0)


@dataclass(frozen=True, slots=True)
class Scope:
    conversation_id: str
    is_dm: bool = False
    linked_conversation_id: str | None = None


@dataclass(slots=True)
class ScopeSession:
    scope: Scope
    client: MucaWsClient
    replies: ReplyDispatcher

    # Set by the voice bridge while the bot is in this scope's voice
    # channel: spoken replies go there.
    on_state_update: StateUpdateHandler | None = None

    async def handle_state_update(self, data: dict) -> None:
        if self.on_state_update is not None:
            await self.on_state_update(data)


class SessionRegistry:
    def __init__(
        self,
        url: str,
        *,
        client_factory: ClientFactory = MucaWsClient,
        reconnect_delays: tuple[float, ...] = RECONNECT_DELAYS_SECONDS,
    ) -> None:
        self._url = url
        self._client_factory = client_factory
        self._reconnect_delays = reconnect_delays
        self._sessions: dict[str, ScopeSession] = {}

        # discord.py runs event handlers concurrently, so two messages for
        # the same scope arriving before the first connect() resolves would
        # otherwise both see "no session" and each open a duplicate -- this
        # makes check-then-create-then-store atomic across those calls.
        self._lock = asyncio.Lock()

    @property
    def sessions(self) -> dict[str, ScopeSession]:
        return self._sessions

    async def get(
        self,
        scope: Scope,
        *,
        reply_channel,
        post_voice_transcripts: bool = False,
    ) -> ScopeSession:
        """The open session for this scope, opening (or reopening) it."""

        async with self._lock:
            existing = self._sessions.get(scope.conversation_id)
            if existing is not None and existing.client.is_open:
                return existing

            replies = (
                existing.replies
                if existing is not None
                else ReplyDispatcher(
                    reply_channel,
                    post_voice_transcripts=post_voice_transcripts,
                )
            )

            client = await self._open(scope)
            session = ScopeSession(scope=scope, client=client, replies=replies)
            if existing is not None:
                # A reopened session keeps whatever the old one was wired to.
                session.on_state_update = existing.on_state_update

            client.on_assistant_text = session.replies.on_delta
            client.on_state_update = session.handle_state_update

            self._sessions[scope.conversation_id] = session
            return session

    async def run(
        self,
        scope: Scope,
        action: Callable[[MucaWsClient], Awaitable[None]],
        *,
        reply_channel,
        post_voice_transcripts: bool = False,
    ) -> ScopeSession:
        """
        Run `action` on the scope's session; if the session turns out to be
        gone, reopen it once and run it again.
        """

        session = await self.get(
            scope,
            reply_channel=reply_channel,
            post_voice_transcripts=post_voice_transcripts,
        )

        try:
            await action(session.client)
        except MucaConnectionLost:
            logger.info("Reopening the session for %s", scope.conversation_id)
            session = await self.get(
                scope,
                reply_channel=reply_channel,
                post_voice_transcripts=post_voice_transcripts,
            )
            await action(session.client)

        return session

    def find(self, conversation_id: str) -> ScopeSession | None:
        return self._sessions.get(conversation_id)

    async def close(self, conversation_id: str) -> None:
        session = self._sessions.pop(conversation_id, None)
        if session is not None:
            await session.client.close()

    async def close_all(self) -> None:
        for conversation_id in list(self._sessions):
            await self.close(conversation_id)

    async def _open(self, scope: Scope) -> MucaWsClient:
        last_error: Exception | None = None

        for delay in self._reconnect_delays:
            if delay:
                await asyncio.sleep(delay)

            client = self._client_factory(
                self._url,
                conversation_id=scope.conversation_id,
                is_dm=scope.is_dm,
                linked_conversation_id=scope.linked_conversation_id,
            )

            try:
                await client.connect()
                return client
            except (OSError, WebSocketException, MucaConnectionLost) as exc:
                last_error = exc
                logger.warning(
                    "Could not reach MUCA-Server for %s: %s",
                    scope.conversation_id,
                    exc,
                )

        raise MucaConnectionLost(scope.conversation_id) from last_error
