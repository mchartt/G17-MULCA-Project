"""
One WebSocket session against MUCA-Server, for one conversation scope.

Speaks the exact protocol muca_server.protocol defines -- imported from the
muca-server package rather than duplicated, so the two sides cannot drift.
Mirrors what MUCA-Server's own tests and the Unity client do over the wire:
connect, give the main agent the AUI instructions (aui/), stand up the
intervention observer, push the roster, then stream
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
    SetCostAlertMessage,
    SetModelMessage,
    UserTextMessage,
)

from . import aui

logger = logging.getLogger(__name__)

NO_SPEAKER = -1

# (text, is_final, modality) -- modality is "text" for a written reply,
# "audio" for the transcript of a spoken one.
AssistantTextHandler = Callable[[str, bool, str], Awaitable[None]]
StateUpdateHandler = Callable[[dict], Awaitable[None]]
ClosedHandler = Callable[[], Awaitable[None]]
ErrorHandler = Callable[[str], Awaitable[None]]


# MUCA-Server closes a session with this ("service restart") when its
# provider connection ended, e.g. OpenAI's 60-minute Realtime limit.
SERVER_RESTART_CLOSE_CODE = 1012

# How long connect() waits for the server to accept the session: its first
# frame (the intervention agent's guid, or an error creating it). A server
# that refuses (too many sessions, no provider) closes without a word.
HANDSHAKE_TIMEOUT_SECONDS = 10.0


class MucaConnectionLost(ConnectionError):
    """The session's socket is gone; a new session has to be opened."""


async def set_server_model(
    url: str,
    admin_token: str,
    model: str,
    *,
    include_intervention: bool = False,
    timeout: float = 15.0,
) -> str | None:
    """
    Change MUCA-Server's realtime model for every conversation. None when it
    worked (the server ends every session, this one included, with 1012),
    otherwise why not.
    """

    try:
        async with websockets.connect(url) as connection:
            # Sent instead of `connect`: the server builds no agents for it,
            # so this works even when the current model can't connect.
            await connection.send(
                SetModelMessage(
                    event="set_model",
                    admin_token=admin_token,
                    model=model,
                    include_intervention=include_intervention,
                ).model_dump_json(by_alias=True)
            )

            async with asyncio.timeout(timeout):
                async for raw in connection:
                    data = json.loads(raw)
                    if data.get("event") == "error":
                        return str(data.get("message"))
    except ConnectionClosed as exc:
        if exc.rcvd is not None and exc.rcvd.code == SERVER_RESTART_CLOSE_CODE:
            return None
        return f"the server closed the connection ({exc})"
    except TimeoutError:
        return "the server didn't answer"
    except OSError as exc:
        return f"couldn't reach the server ({exc})"

    return "the server closed the connection"


async def set_server_cost_alert(
    url: str,
    admin_token: str,
    *,
    webhook_url: str | None = None,
    threshold_usd: float | None = None,
    timeout: float = 15.0,
) -> str | None:
    """
    Change MUCA-Server's cost-alert webhook/threshold. None when it worked
    (the server closes with 1000, no session needs to reopen for this --
    unlike set_server_model), otherwise why not.
    """

    try:
        async with websockets.connect(url) as connection:
            await connection.send(
                SetCostAlertMessage(
                    event="set_cost_alert",
                    admin_token=admin_token,
                    webhook_url=webhook_url,
                    threshold_usd=threshold_usd,
                ).model_dump_json(by_alias=True)
            )

            async with asyncio.timeout(timeout):
                async for raw in connection:
                    data = json.loads(raw)
                    if data.get("event") == "error":
                        return str(data.get("message"))

            # Unlike set_server_model's 1012, a clean 1000 close (this
            # function's own success code) ends the above loop normally
            # without ever raising ConnectionClosed -- there is nothing to
            # catch below for it, so the close code has to be read here.
            if connection.close_code == 1000:
                return None
    except ConnectionClosed as exc:
        return f"the server closed the connection ({exc})"
    except TimeoutError:
        return "the server didn't answer"
    except OSError as exc:
        return f"couldn't reach the server ({exc})"

    return "the server closed the connection"


class MucaWsClient:
    def __init__(
        self,
        url: str,
        *,
        conversation_id: str,
        is_dm: bool,
        linked_conversation_id: str | None = None,
        bot_name: str = "",
        main_model: str = "",
        intervention_model: str = "",
    ) -> None:
        self._url = url
        # This session's own realtime models; "" is the server's.
        self._main_model = main_model
        self._intervention_model = intervention_model
        self._conversation_id = conversation_id
        self._bot_name = bot_name
        self._is_dm = is_dm
        # For a DM only: the group conversation_id of the linked channel
        # its sender last spoke in (and can still see), so MUCA-Server can
        # give this DM one-way read access to that group's memory. None if
        # there's none.
        self._linked_conversation_id = linked_conversation_id
        self._connection: ClientConnection | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._open = False

        # How the server ended the session, once it has: 1012 means it
        # restarted it on purpose (its provider connection ended).
        self.close_code: int | None = None

        # Guids of the observers the server created for this session.
        self.agent_guids: list[str] = []
        self._accepted = asyncio.Event()

        # Set by the caller before connect().
        self.on_assistant_text: AssistantTextHandler | None = None
        self.on_state_update: StateUpdateHandler | None = None
        self.on_closed: ClosedHandler | None = None
        self.on_error: ErrorHandler | None = None

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
                bot_name=self._bot_name,
                main_model=self._main_model,
                intervention_model=self._intervention_model,
            )
        )
        # The AUI teaching assistant: MUCA-Server's main agent is generic
        # until this replaces its instructions (a raw provider session.update).
        await self._connection.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {"instructions": aui.main_instructions()},
                }
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

        # Open only once the server accepted it: one that refuses (too many
        # sessions, or no provider) closes the socket instead, and a message
        # sent meanwhile would be lost without a word.
        accepted = asyncio.create_task(self._accepted.wait())
        await asyncio.wait(
            {accepted, self._receive_task},
            timeout=HANDSHAKE_TIMEOUT_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        accepted.cancel()
        if not self._accepted.is_set():
            await self.close()
            raise MucaConnectionLost(self._conversation_id)

    async def send_participants(
        self,
        participants: dict[int, str],
        *,
        modality: str = "text",
    ) -> None:
        await self._send(
            ParticipantsMessage(
                event="participants",
                participants=[
                    Participant(id=user_id, name=name)
                    for user_id, name in participants.items()
                ],
                modality=modality,
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

    async def close(self, *, wait_for_server: float | None = None) -> bool:
        """
        End the session. With `wait_for_server`, first wait up to that many
        seconds for the server to close the socket itself, and say whether
        it did: the server closes it only after it has closed the
        conversation, saving its memory -- so a session reopened after a
        True can't load memory older than this one's.
        """

        if self._connection is None:
            return False

        if self._open:
            with suppress(Exception):
                await self._send(DisconnectMessage(event="disconnect"))

        # From here on the socket's end is expected, not "lost".
        self._open = False

        server_closed = False
        if wait_for_server is not None and self._receive_task is not None:
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._receive_task),
                    timeout=wait_for_server,
                )
                server_closed = True
            except (asyncio.TimeoutError, Exception):
                pass

        with suppress(Exception):
            await self._connection.close()

        if self._receive_task is not None:
            self._receive_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await self._receive_task
            self._receive_task = None

        return server_closed

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
            self.close_code = getattr(self._connection, "close_code", None)
            was_open, self._open = self._open, False
            if was_open and self.close_code == SERVER_RESTART_CLOSE_CODE:
                logger.info(
                    "MUCA-Server restarted the session for %s; it reopens "
                    "on next use",
                    self._conversation_id,
                )
            elif was_open:
                logger.warning(
                    "Lost MUCA-Server session for %s (close code %s)",
                    self._conversation_id,
                    self.close_code,
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
        self._accepted.set()

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
                if self.on_error is not None:
                    await self.on_error(str(data.get("message")))
            else:
                # agent_message: observability only.
                logger.debug("server event %s: %s", event, data)
        except Exception:
            # A Discord API failure while posting a reply must not end the
            # session's receive loop.
            logger.exception("Handling %s failed", event)
