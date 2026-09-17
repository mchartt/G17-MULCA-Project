"""
One WebSocket session against MUCA-Server, for one conversation scope.

Speaks the exact protocol muca_server.protocol defines -- imported from the
muca-server package rather than duplicated, so the two sides cannot drift.
Mirrors what MUCA-Server's own tests and the Unity client do over the wire:
connect, stand up the intervention observer, push the roster, then stream
user_text turns and read assistant_text back.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

import websockets
from websockets.asyncio.client import ClientConnection

from muca_server.agents.options import INTERVENTION_DETECTION
from muca_server.protocol import (
    ConnectAgentMessage,
    CreateAuxiliaryAgentMessage,
    IncomingMessage,
    Participant,
    ParticipantsMessage,
    UserTextMessage,
)

logger = logging.getLogger(__name__)

AssistantTextHandler = Callable[[str, bool], Awaitable[None]]


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

        # Set by the caller before receive_loop() starts consuming.
        self.on_assistant_text: AssistantTextHandler | None = None

    async def connect(self) -> None:
        self._connection = await websockets.connect(self._url)

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

    async def receive_loop(self) -> None:
        assert self._connection is not None

        async for raw in self._connection:
            await self._handle_raw(raw)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()

    async def _send(self, message: IncomingMessage) -> None:
        assert self._connection is not None
        await self._connection.send(message.model_dump_json(by_alias=True))

    async def _handle_raw(self, raw: str | bytes) -> None:
        data = json.loads(raw)
        event = data.get("event")

        if event == "assistant_text":
            if self.on_assistant_text is not None:
                await self.on_assistant_text(
                    data.get("text", ""),
                    data.get("isFinal", False),
                )
            return

        # agent_message / agent_guid / state_update: observability only, no
        # adapter behaviour depends on them yet.
        logger.debug("[MULCA debug] server event %s: %s", event, data)
