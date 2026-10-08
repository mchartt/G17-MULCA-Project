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
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field

from websockets.exceptions import WebSocketException

from .dispatch import ReplyDispatcher
from .muca_client import MucaConnectionLost, MucaWsClient

logger = logging.getLogger(__name__)

ClientFactory = Callable[..., MucaWsClient]
StateUpdateHandler = Callable[[dict], Awaitable[None]]
ListeningStateHandler = Callable[[bool], Awaitable[None]]
# (session, is_final) for each piece of a reply; (session, message) for an
# error the server reported.
ReplyHook = Callable[["ScopeSession", bool], None]
ServerErrorHook = Callable[["ScopeSession", str], Awaitable[None]]
UsageHook = Callable[["ScopeSession", dict], Awaitable[None]]

# Waits between attempts to (re)open a session.
RECONNECT_DELAYS_SECONDS = (0.0, 0.5, 1.0, 2.0)

# A session that ends sooner than this after opening (e.g. the server can't
# connect to its provider, so every new session dies at once) is reopened
# only after a wait, doubling each time up to the maximum -- voice ticks
# every 100 ms and would otherwise reopen it ten times a second.
SHORT_LIVED_SECONDS = 10.0
SHORT_LIVED_BACKOFF_SECONDS = (1.0, 30.0)

# How long a restart waits for the server to confirm the old session saved
# its memory before the new one is opened.
RESTART_WAIT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class Scope:
    conversation_id: str
    is_dm: bool = False
    linked_conversation_id: str | None = None
    # Which bot this scope belongs to, purely for MUCA-Server's cost-report
    # attribution (usage_report.py) -- conversation_id alone never reveals
    # that, since many bots share one MUCA-Server.
    bot_name: str = ""
    # This link's own listening mode (Link.listening_mode), overriding
    # MUCA-Server's own default -- "" means unset/use the server's.
    listening_mode: str = ""


@dataclass(slots=True)
class ScopeSession:
    scope: Scope
    client: MucaWsClient
    replies: ReplyDispatcher

    # Set by the voice bridge while the bot is in this scope's voice
    # channel: spoken replies go there.
    on_state_update: StateUpdateHandler | None = None
    # Set by the voice bridge too: a chime when MULCA starts or stops
    # listening, for people who aren't watching the text channel.
    on_listening_state: ListeningStateHandler | None = None

    opened_at: float = field(default_factory=time.monotonic)

    async def handle_state_update(self, data: dict) -> None:
        if self.on_state_update is not None:
            await self.on_state_update(data)

    async def handle_listening_state(self, open_: bool) -> None:
        """
        "wake" mode: MUCA-Server started or ended an engaged session.
        "transcribe" opens and closes a 5 s window on every wake phrase,
        too often to announce. ("toggle" never gets here: arm_listening
        takes these replies itself.)
        """

        if self.scope.listening_mode == "transcribe":
            return

        name = self.scope.bot_name or "MULCA"
        channel = self.replies.channel
        if channel is not None:
            await channel.send(
                f"\N{STUDIO MICROPHONE} {name} is listening"
                if open_
                else f"\N{SLEEPING SYMBOL} {name} went back to sleep"
            )
        if self.on_listening_state is not None:
            await self.on_listening_state(open_)


class SessionRegistry:
    def __init__(
        self,
        url: str,
        *,
        client_factory: ClientFactory = MucaWsClient,
        reconnect_delays: tuple[float, ...] = RECONNECT_DELAYS_SECONDS,
        models: Callable[[], tuple[str, str]] = lambda: ("", ""),
    ) -> None:
        self._url = url
        # The (main, intervention) models a new session asks the server for;
        # "" means the server's own.
        self._models = models
        self._client_factory = client_factory
        self._reconnect_delays = reconnect_delays
        self._sessions: dict[str, ScopeSession] = {}

        # discord.py runs event handlers concurrently, so two messages for
        # the same scope arriving before the first connect() resolves would
        # otherwise both see "no session" and each open a duplicate -- this
        # makes check-then-create-then-store atomic across those calls. One
        # lock per scope: a restart holding it (waiting for the server to
        # save) must not hold up every other scope.
        self._locks: dict[str, asyncio.Lock] = {}
        self._backoff: dict[str, float] = {}

        # Set by the bot (BotRuntime): replies count as activity, and the
        # server's errors are told to the users.
        self.on_reply: ReplyHook | None = None
        self.on_server_error: ServerErrorHook | None = None
        # Set by the bot too: what each server call cost, and whether its
        # sessions answer every turn in text (set_text_replies).
        self.on_usage: UsageHook | None = None
        self.text_replies = False

    @property
    def url(self) -> str:
        return self._url

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

        async with self._lock_for(scope.conversation_id):
            existing = self._sessions.get(scope.conversation_id)
            if existing is not None and existing.client.is_open:
                return existing

            if existing is not None:
                await self._wait_if_short_lived(existing)

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
                session.on_listening_state = existing.on_listening_state

            async def on_text(text: str, is_final: bool, modality: str = "text") -> None:
                if self.on_reply is not None:
                    self.on_reply(session, is_final)
                await session.replies.on_delta(text, is_final, modality)

            async def on_error(message: str) -> None:
                if self.on_server_error is not None:
                    await self.on_server_error(session, message)

            async def on_usage(usage: dict) -> None:
                if self.on_usage is not None:
                    await self.on_usage(session, usage)

            client.on_assistant_text = on_text
            client.on_error = on_error
            client.on_usage = on_usage
            client.on_state_update = session.handle_state_update
            client.on_listening_state = session.handle_listening_state

            self._sessions[scope.conversation_id] = session
            logger.info(
                "Opened the session for %s (%d open)",
                scope.conversation_id,
                self.open_count(),
            )
            return session

    async def run(
        self,
        scope: Scope,
        action: Callable[[MucaWsClient], Awaitable[None]],
        *,
        reply_channel,
        post_voice_transcripts: bool = False,
        retry_once: bool = True,
    ) -> ScopeSession:
        """
        Run `action` on the scope's session; if the session turns out to be
        gone, reopen it once and run it again -- unless `retry_once` is
        False, since a websocket send can raise a connection error even
        after the bytes already reached the server (the disconnect can be
        detected slightly after the write succeeds), and retrying an action
        that triggers a real cognitive turn (a user's text message) risks
        running that turn twice on two independent sessions, not just
        resending an inert frame. Continuous, harmless-to-repeat actions
        (voice frames) should keep the default; a one-shot, turn-triggering
        action should pass retry_once=False and let MucaConnectionLost
        propagate, so the caller's existing "log and drop this one message"
        handling applies instead of silently duplicating it.
        """

        session = await self.get(
            scope,
            reply_channel=reply_channel,
            post_voice_transcripts=post_voice_transcripts,
        )

        try:
            await action(session.client)
        except MucaConnectionLost:
            if not retry_once:
                raise

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

    async def close(
        self,
        conversation_id: str,
        *,
        wait: float | None = None,
    ) -> bool:
        """
        Close the scope's session. With `wait`, wait up to that long for
        the server to confirm it saved the conversation, and say whether it
        did (True also when there was no open session, so nothing to save).
        The scope stays locked meanwhile, so nothing reopens it early.
        """

        async with self._lock_for(conversation_id):
            session = self._sessions.pop(conversation_id, None)
            self._backoff.pop(conversation_id, None)
            if session is None or not session.client.is_open:
                return True

            saved = await session.client.close(wait_for_server=wait)
            logger.info(
                "Closed the session for %s (%d open)",
                conversation_id,
                self.open_count(),
            )
            return saved

    async def restart(
        self,
        conversation_id: str,
        *,
        wait: float = RESTART_WAIT_SECONDS,
    ) -> bool:
        """
        End the scope's session so that its next use opens a fresh one: new
        provider connections on the server, the same memory. Says whether
        the server confirmed it saved that memory first.
        """

        logger.info("Restarting the session for %s", conversation_id)
        return await self.close(conversation_id, wait=wait)

    async def close_all(self) -> None:
        for conversation_id in list(self._sessions):
            await self.close(conversation_id)

    def open_count(self) -> int:
        return sum(1 for session in self._sessions.values() if session.client.is_open)

    def _lock_for(self, conversation_id: str) -> asyncio.Lock:
        return self._locks.setdefault(conversation_id, asyncio.Lock())

    async def _wait_if_short_lived(self, ended: ScopeSession) -> None:
        conversation_id = ended.scope.conversation_id
        if time.monotonic() - ended.opened_at >= SHORT_LIVED_SECONDS:
            self._backoff.pop(conversation_id, None)
            return

        first, maximum = SHORT_LIVED_BACKOFF_SECONDS
        previous = self._backoff.get(conversation_id)
        delay = first if previous is None else min(previous * 2, maximum)
        self._backoff[conversation_id] = delay

        logger.warning(
            "The session for %s ended %.1f s after opening; reopening in %.0f s",
            conversation_id,
            time.monotonic() - ended.opened_at,
            delay,
        )
        await asyncio.sleep(delay)

    async def set_text_replies(self, text_replies: bool) -> None:
        """Every open session, and every later one, answers in text (or not)."""

        if text_replies == self.text_replies:
            return

        self.text_replies = text_replies
        for session in list(self._sessions.values()):
            if session.client.is_open:
                with suppress(MucaConnectionLost):
                    await session.client.set_text_replies(text_replies)

    async def _open(self, scope: Scope) -> MucaWsClient:
        last_error: Exception | None = None

        for delay in self._reconnect_delays:
            if delay:
                await asyncio.sleep(delay)

            main_model, intervention_model = self._models()
            client = self._client_factory(
                self._url,
                conversation_id=scope.conversation_id,
                is_dm=scope.is_dm,
                linked_conversation_id=scope.linked_conversation_id,
                bot_name=scope.bot_name,
                listening_mode=scope.listening_mode,
                main_model=main_model,
                intervention_model=intervention_model,
            )

            client.text_replies = self.text_replies
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
