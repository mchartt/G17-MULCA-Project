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
from collections.abc import Awaitable, Callable
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

# A tick taking this long means something inside it is stuck, not just
# slow -- see _run()'s use of this as an asyncio.wait_for timeout.
TICK_HANG_SECONDS = 2.0

# Watchdog: consecutive tick failures before trying to recover, not one
# transient blip -- see _watchdog_tick_failed.
WATCHDOG_FAILURE_THRESHOLD = 3

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
        on_unhealthy: Callable[[], Any] | None = None,
        on_active: Callable[[], Awaitable[bool]] | None = None,
        on_reachable: Callable[[bool], Awaitable[None]] | None = None,
    ) -> None:
        self._scope = scope
        self._registry = registry
        self._voice_client = voice_client
        self._reply_channel = reply_channel
        self._post_voice_transcripts = post_voice_transcripts
        self._roster = roster
        # Watchdog tier 2: a full leave-and-rejoin of the voice channel,
        # since that needs the Discord-side join/leave this object has no
        # reference to (discord_client.py owns client.mulca_voice). Fine to
        # reach whenever tier 1 (just reopening the MUCA-Server session)
        # doesn't verifiably fix things -- not a scary last resort to avoid.
        self._on_unhealthy = on_unhealthy
        # Someone holds the floor or MULCA is heard: False means the bot is
        # out of voice for its spending limit (send nothing). And
        # whether MUCA-Server could be reached, for the users to hear of.
        self._on_active = on_active
        self._on_reachable = on_reachable

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
        # Watchdog: consecutive tick failures (hangs, or MUCA-Server
        # unreachable) since the last success -- one transient blip isn't
        # worth reacting to, several in a row is.
        self._consecutive_tick_failures = 0

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
        self._task.add_done_callback(self._report_if_run_died)

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
            await self._send(
                lambda client: client.send_participants(roster, modality="audio"),
            )
        except MucaConnectionLost:
            logger.warning("MUCA-Server unreachable; roster not sent")

    def forget(self, user_id: int) -> None:
        self.capture.forget(user_id)

    # ------------------------------------------------------------------

    def _report_if_run_died(self, task: asyncio.Task) -> None:
        """
        _run()'s own while-True loop already catches every exception it
        knows about and keeps going -- it should never actually finish on
        its own. If it ever does (a bug in that loop itself, not something
        _tick() raised), this is otherwise a silent voice outage: nothing
        else would notice or log it, matching exactly a reported freeze
        where voice stopped doing anything with no error anywhere.

        Watchdog tier 2 directly, no tier 1 attempt: there's no loop left
        to retry a tick from, so "just reopen the session" isn't an option
        the way it is in _watchdog_tick_failed -- a full leave-and-rejoin
        is the only recovery available here.
        """

        if task.cancelled():
            return

        exc = task.exception()
        if exc is not None:
            logger.error(
                "Voice for %s: its tick loop died unexpectedly (bug, not "
                "a per-tick failure -- those are already caught inside "
                "_run()); recovering with a full leave-and-rejoin",
                self._scope.conversation_id,
                exc_info=exc,
            )
        else:
            logger.error(
                "Voice for %s: its tick loop returned instead of looping "
                "forever; recovering with a full leave-and-rejoin",
                self._scope.conversation_id,
            )

        if self._on_unhealthy is not None:
            # A done-callback must be sync; on_unhealthy is a coroutine.
            asyncio.create_task(
                self._on_unhealthy(),
                name=f"voice-watchdog-recover-{self._scope.conversation_id}",
            )

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(TICK_SECONDS)

            try:
                # Debugging a reported freeze where voice silently stopped
                # doing anything at all, on either side, with no exception
                # and no further logs: a genuine hang inside _tick() (a
                # websocket send that never resolves, a lock that never
                # releases) would otherwise block this loop forever with
                # nothing to catch it -- a bare `except Exception` only
                # catches a tick that *fails*, not one that never returns.
                # wait_for forces it to surface as a loud, specific error
                # instead of silence.
                await asyncio.wait_for(self._tick(), timeout=TICK_HANG_SECONDS)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                logger.error(
                    "Voice tick for %s did not finish within %.0fs -- "
                    "something inside _tick() is stuck (not failing, "
                    "genuinely hanging). Retrying next tick.",
                    self._scope.conversation_id,
                    TICK_HANG_SECONDS,
                )
                await self._watchdog_tick_failed()
            except MucaConnectionLost:
                # The registry reopens the session on the next tick.
                logger.warning(
                    "Voice for %s: MUCA-Server unreachable",
                    self._scope.conversation_id,
                )
                if self._on_reachable is not None:
                    await self._on_reachable(False)
                await asyncio.sleep(1)
                await self._watchdog_tick_failed()
            except Exception:
                logger.exception("Voice tick failed")
                await self._watchdog_tick_failed()
            else:
                self._consecutive_tick_failures = 0
                if self._on_reachable is not None:
                    await self._on_reachable(True)

    async def _watchdog_tick_failed(self) -> None:
        """
        Covers two real causes uniformly, without needing to know which
        one actually happened: OpenAI's 60-minute Realtime session limit
        (MUCA-Server saves and ends the session; the client should just
        reopen it), and an otherwise-unexplained stall. One failed tick
        isn't worth reacting to -- a network blip, a slow response -- but
        several in a row means something is actually wrong.
        """

        self._consecutive_tick_failures += 1
        if self._consecutive_tick_failures < WATCHDOG_FAILURE_THRESHOLD:
            return

        self._consecutive_tick_failures = 0
        logger.warning(
            "[watchdog] %s unhealthy after %d consecutive tick failures; "
            "reopening the MUCA-Server session",
            self._scope.conversation_id,
            WATCHDOG_FAILURE_THRESHOLD,
        )
        await self._registry.close(self._scope.conversation_id)

        # Tier 1: does a fresh session alone fix it? Only logged if it
        # doesn't -- a successful recovery falls through silently, same as
        # any other healthy tick.
        try:
            await asyncio.wait_for(self._tick(), timeout=TICK_HANG_SECONDS)
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "[watchdog] %s still unhealthy after reopening the "
                "session; escalating to a full leave-and-rejoin",
                self._scope.conversation_id,
            )

        # Tier 2: fine to reach whenever tier 1 doesn't verifiably work --
        # not a scary last resort reserved for rare cases. Scheduled rather
        # than awaited: we're still inside _run()'s own task, and
        # on_unhealthy ends up calling disconnect(), which cancels and
        # awaits that same task -- awaiting it directly here would be the
        # task waiting on itself.
        if self._on_unhealthy is not None:
            asyncio.create_task(
                self._on_unhealthy(),
                name=f"voice-watchdog-recover-{self._scope.conversation_id}",
            )

    async def _tick(self) -> None:
        speaker, samples = self.synchronizer.take_frame(_now_ms())
        played = self.player.take_played()

        if (
            (speaker is not None or played)
            and self._on_active is not None
            and not await self._on_active()
        ):
            return

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
                await client.send_participants(self._roster(), modality="audio")

    async def _on_state_update(self, data: dict) -> None:
        if data.get("clearAudioQueue"):
            # debug, not info: fires on every barge-in, not just rare
            # anomalies -- the exception handler below stays loud, since
            # that's a genuine failure, not routine chatter.
            logger.debug(
                "[voice-turn] %s clearAudioQueue received -- clearing "
                "player and stopping playback",
                self._scope.conversation_id,
            )
            self.player.clear()
            try:
                # stop_playing(), not stop(): VoiceRecvClient.stop() is
                # "stop playing AND receiving" -- it calls
                # stop_listening(), which tears down the receive sink
                # permanently (self._reader = MISSING) and nothing ever
                # calls listen() again. That silently and permanently
                # killed voice input the moment anyone first interrupted
                # MULCA -- confirmed live: the capture stats (packet
                # counts) froze at the exact same number forever after an
                # interrupt, while the tick loop and text kept working.
                self._voice_client.stop_playing()
            except Exception:
                # Was a bare suppress(Exception) -- silent. If this is
                # where playback fails to actually stop (MULCA keeps
                # talking over the user), this is what would show it.
                logger.exception(
                    "[voice-turn] %s voice_client.stop_playing() failed "
                    "during clearAudioQueue -- playback may not actually "
                    "have stopped",
                    self._scope.conversation_id,
                )

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
