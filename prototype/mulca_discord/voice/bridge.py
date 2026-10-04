"""
One instance's voice channel, wired to its MUCA-Server session.

Every tick (100 ms) the current speaker's audio goes up as one audio_stream
frame, together with the playback state -- also when nobody speaks, so the
server always knows whether MULCA is still audible. Spoken replies come
back in state_update frames and are played into the channel; a
clearAudioQueue (the users talked over MULCA) silences it at once.

The session is the instance's own (conversation_id "instance:<name>"), the
same one its text channel uses, so text and voice share one memory.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..muca_client import MucaConnectionLost, MucaWsClient
from ..sessions import Scope, SessionRegistry
from .capture import VoiceCapture
from .debug import UpstreamRecorder
from .player import AssistantPlayer
from .synchronizer import SpeakerSynchronizer

logger = logging.getLogger(__name__)

TICK_SECONDS = 0.1
TICK_SAMPLES = 2400  # 100 ms at 24 kHz

# How often the capture counters are logged while in voice.
STATS_INTERVAL_SECONDS = 10.0

# Set to a directory to record exactly what MUCA-Server hears.
DEBUG_DIR_ENV_VAR = "MULCA_VOICE_DEBUG_DIR"


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _encode(samples: np.ndarray) -> str:
    if samples.size == 0:
        return ""

    return base64.b64encode(samples.astype("<f4").tobytes()).decode("ascii")


class VoiceBridge:
    def __init__(
        self,
        *,
        scope: Scope,
        registry: SessionRegistry,
        voice_client: Any,
        reply_channel,
        post_voice_transcripts: bool = False,
        roster: Callable[[], dict[int, str]] = dict,
    ) -> None:
        self._scope = scope
        self._registry = registry
        self._voice_client = voice_client
        self._reply_channel = reply_channel
        self._post_voice_transcripts = post_voice_transcripts
        self._roster = roster

        self.synchronizer = SpeakerSynchronizer()
        self.player = AssistantPlayer()
        self.capture = VoiceCapture(
            self.synchronizer,
            dave_session=self._dave_session,
        )

        self._task: asyncio.Task[None] | None = None
        self._last_speaker: int | None = None
        self._last_client: MucaWsClient | None = None
        self._last_stats = time.monotonic()
        self._recorder: UpstreamRecorder | None = None

    async def start(self) -> None:
        debug_dir = os.environ.get(DEBUG_DIR_ENV_VAR)
        if debug_dir:
            name = (
                self._scope.conversation_id.replace(":", "_")
                + datetime.now().strftime("-%Y%m%d-%H%M%S")
            )
            self._recorder = UpstreamRecorder(Path(debug_dir), name)
            logger.info(
                "Recording what MUCA-Server hears to %s",
                self._recorder.audio.path,
            )

        self._voice_client.listen(self.capture)
        await self.update_participants()
        self._task = asyncio.create_task(
            self._run(),
            name=f"voice-{self._scope.conversation_id}",
        )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

        with suppress(Exception):
            self._voice_client.stop_listening()
        with suppress(Exception):
            self._voice_client.stop()

        self.player.clear()

        if self._recorder is not None:
            self._recorder.close()
            self._recorder = None

        logger.info(
            "Voice for %s ended: %s",
            self._scope.conversation_id,
            self.capture.stats(),
        )

    async def disconnect(self) -> None:
        """Stop, and leave the voice channel."""

        await self.stop()
        with suppress(Exception):
            await self._voice_client.disconnect(force=True)

    async def update_participants(self) -> None:
        roster = self._roster()
        try:
            await self._send(lambda client: client.send_participants(roster))
        except MucaConnectionLost:
            logger.warning("MUCA-Server unreachable; roster not sent")

    def forget(self, user_id: int) -> None:
        self.capture.forget(user_id)

    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(TICK_SECONDS)

            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except MucaConnectionLost:
                # The registry reopens the session on the next tick.
                logger.warning(
                    "Voice for %s: MUCA-Server unreachable",
                    self._scope.conversation_id,
                )
                await asyncio.sleep(1)
            except Exception:
                logger.exception("Voice tick failed")

    async def _tick(self) -> None:
        speaker, samples = self.synchronizer.take_frame(_now_ms())
        played = self.player.take_played()

        if self._recorder is not None:
            self._recorder.write_tick(speaker, samples, TICK_SAMPLES)

        if time.monotonic() - self._last_stats >= STATS_INTERVAL_SECONDS:
            self._last_stats = time.monotonic()
            logger.info(
                "Voice for %s: %s",
                self._scope.conversation_id,
                self.capture.stats(),
            )

        if speaker != self._last_speaker and speaker is not None:
            # A newcomer to the floor: make sure the server knows their name.
            await self.update_participants()
        self._last_speaker = speaker

        async def send(client: MucaWsClient) -> None:
            await client.send_audio_stream(
                speaker=speaker,
                audio=_encode(samples),
                is_notifying=self.player.is_notifying(),
                playback_time_ms=self.player.playback_time_ms(),
            )
            if played:
                await client.send_playback_frame(
                    base64.b64encode(played).decode("ascii"),
                )

        await self._send(send)

    async def _send(self, action) -> None:
        session = await self._registry.run(
            self._scope,
            action,
            reply_channel=self._reply_channel,
            post_voice_transcripts=self._post_voice_transcripts,
        )
        session.on_state_update = self._on_state_update

        client = getattr(session, "client", None)
        if client is not self._last_client:
            new_session = self._last_client is not None
            self._last_client = client
            if new_session:
                # The session was reopened (a /restart, the server ending
                # it, a server restart): the new one knows nobody yet, and
                # whatever the old one still had queued to say is stale.
                self.player.clear()
                await client.send_participants(self._roster())

    async def _on_state_update(self, data: dict) -> None:
        if data.get("clearAudioQueue"):
            self.player.clear()
            with suppress(Exception):
                self._voice_client.stop()

        audio = data.get("audio")
        if audio:
            self.player.enqueue(base64.b64decode(audio))
            self._ensure_playing()

    def _ensure_playing(self) -> None:
        voice_client = self._voice_client
        if not voice_client.is_connected() or voice_client.is_playing():
            return

        try:
            voice_client.play(self.player)
        except Exception:
            logger.exception("Could not start playback")

    def _dave_session(self):
        connection = getattr(self._voice_client, "_connection", None)
        return getattr(connection, "dave_session", None)
