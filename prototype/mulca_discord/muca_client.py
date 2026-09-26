"""
One WebSocket session against MUCA-Server, for one conversation scope.

Speaks the exact protocol muca_server.protocol defines -- imported from the
muca-server package rather than duplicated, so the two sides cannot drift.
Mirrors what MUCA-Server's own tests and the Unity client do over the wire:
connect, stand up the intervention observer, push the roster, then stream
user_text turns (and, for voice, audio_stream frames) and read
assistant_text / state_update back. See MUCA-Server's docs/PROTOCOL.md.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

from muca_server.agents.options import INTERVENTION_DETECTION
from muca_server.protocol import (
    AudioStreamMessage,
    ConnectAgentMessage,
    CreateAuxiliaryAgentMessage,
    DisconnectMessage,
    IncomingMessage,
    Participant,
    ParticipantsMessage,
    PlaybackFrameMessage,
    UserTextMessage,
)

logger = logging.getLogger(__name__)

NO_SPEAKER = -1

# (text, is_final, modality) -- modality is "text" for a written reply,
# "audio" for the transcript of a spoken one.
AssistantTextHandler = Callable[[str, bool, str], Awaitable[None]]
StateUpdateHandler = Callable[[dict], Awaitable[None]]
ClosedHandler = Callable[[], Awaitable[None]]


class MucaConnectionLost(ConnectionError):
    """The session's socket is gone; a new session has to be opened."""


class MucaWsClient:
    def __init__(
        self,
        url: str,
        *,
        conversation_id: str,
        is_dm: bool,
        linked_conversation_id: str | None = None,
    ) -> None:
        self._url = url
        self._conversation_id = conversation_id
        self._is_dm = is_dm
        # For a DM only: the group conversation_id its sender is a
        # recognized participant of (instances.py), so MUCA-Server can give
        # this DM one-way read access to that group's memory. None if the
        # sender isn't recognized as belonging to any instance.
        self._linked_conversation_id = linked_conversation_id
        self._connection: ClientConnection | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._open = False

        # Guids of the observers the server created for this session.
        self.agent_guids: list[str] = []

        # Set by the caller before connect().
        self.on_assistant_text: AssistantTextHandler | None = None
        self.on_state_update: StateUpdateHandler | None = None
        self.on_closed: ClosedHandler | None = None

    @property
    def conversation_id(self) -> str:
        return self._conversation_id

    @property
    def is_open(self) -> bool:
        return self._open

    async def connect(self) -> None:
        self._connection = await websockets.connect(
            self._url,
            # A spoken reply arrives as a burst of audio frames, generated
            # faster than it plays; don't let the read buffer throttle it.
            max_queue=None,
        )
        self._open = True

        await self._send(
            ConnectAgentMessage(
                event="connect",
                conversation_id=self._conversation_id,
                is_dm=self._is_dm,
                linked_conversation_id=self._linked_conversation_id,
            )
        )
        await self._send(
            CreateAuxiliaryAgentMessage(
                event="create_auxiliary_agent",
                auxiliary_agent_type=INTERVENTION_DETECTION,
            )
        )

        self._receive_task = asyncio.create_task(
            self._receive_loop(),
            name=f"muca-receive-{self._conversation_id}",
        )

    async def send_participants(
        self,
        participants: dict[int, str],
    ) -> None:
        await self._send(
            ParticipantsMessage(
                event="participants",
                participants=[
                    Participant(id=user_id, name=name)
                    for user_id, name in participants.items()
                ],
            )
        )

    async def send_user_text(
        self,
        *,
        speaker: int,
        speaker_name: str,
        text: str,
    ) -> None:
        await self._send(
            UserTextMessage(
                event="user_text",
                speaker=speaker,
                speaker_name=speaker_name,
                text=text,
            )
        )

    async def send_audio_stream(
        self,
        *,
        speaker: int | None,
        audio: str,
        is_notifying: bool,
        playback_time_ms: int,
    ) -> None:
        """
        One tick of voice: the current speaker's audio (base64 float32,
        mono, 24 kHz), or none -- sent every tick even when nobody speaks,
        so the server always knows the playback state.
        """

        await self._send(
            AudioStreamMessage(
                event="audio_stream",
                speaker=speaker if speaker is not None else NO_SPEAKER,
                is_notifying=is_notifying,
                playback_time_ms=playback_time_ms,
                audio=audio,
            )
        )

    async def send_playback_frame(self, audio: str) -> None:
        """Assistant audio the users just heard, for the observers."""

        await self._send(
            PlaybackFrameMessage(event="playback_frame", audio=audio),
        )

    async def close(self) -> None:
        if self._connection is None:
            return

        if self._open:
            with suppress(Exception):
                await self._send(DisconnectMessage(event="disconnect"))

        self._open = False

        with suppress(Exception):
            await self._connection.close()

        if self._receive_task is not None:
            self._receive_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._receive_task
            self._receive_task = None

    async def _send(self, message: IncomingMessage) -> None:
        if self._connection is None or not self._open:
            raise MucaConnectionLost(self._conversation_id)

        try:
            await self._connection.send(
                message.model_dump_json(by_alias=True),
            )
        except ConnectionClosed as exc:
            self._open = False
            raise MucaConnectionLost(self._conversation_id) from exc

    async def _receive_loop(self) -> None:
        assert self._connection is not None

        try:
            async for raw in self._connection:
                await self._handle_raw(raw)
        except ConnectionClosed:
            pass
        finally:
            was_open, self._open = self._open, False
            if was_open:
                logger.warning(
                    "Lost MUCA-Server session for %s",
                    self._conversation_id,
                )
            if self.on_closed is not None:
                with suppress(Exception):
                    await self.on_closed()

    async def _handle_raw(self, raw: str | bytes) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Unreadable frame from MUCA-Server: %r", raw[:200])
            return

        event = data.get("event")

        try:
            if event == "assistant_text":
                if self.on_assistant_text is not None:
                    await self.on_assistant_text(
                        data.get("text", ""),
                        data.get("isFinal", False),
                        data.get("modality", "text"),
                    )
            elif event == "state_update":
                if self.on_state_update is not None:
                    await self.on_state_update(data)
            elif event == "agent_guid":
                self.agent_guids.append(data.get("guid", ""))
            elif event == "error":
                logger.warning(
                    "MUCA-Server reported an error for %s: %s",
                    self._conversation_id,
                    data.get("message"),
                )
            else:
                # agent_message: observability only.
                logger.debug("server event %s: %s", event, data)
        except Exception:
            # A Discord API failure while posting a reply must not end the
            # session's receive loop.
            logger.exception("Handling %s failed", event)
