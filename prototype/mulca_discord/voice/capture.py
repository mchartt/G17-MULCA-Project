"""
Hears each user in the voice channel separately.

discord-ext-voice-recv hands over each user's Opus packets. Discord's voice
channels may be end-to-end encrypted (DAVE), which that library does not
undo, so this sink takes the Opus itself, removes the DAVE layer with
discord.py's own DAVE session when there is one, and decodes it.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable
from typing import Any

import numpy as np
from discord.ext import voice_recv
from discord.ext.voice_recv.rtp import FakePacket
from discord.opus import Decoder

from .player import discord_audio_to_server
from .synchronizer import SpeakerSynchronizer

logger = logging.getLogger(__name__)

try:
    import davey

    DAVE_AUDIO = davey.MediaType.audio
except ImportError:  # pragma: no cover - davey ships with discord.py[voice]
    davey = None
    DAVE_AUDIO = None

DaveSessionGetter = Callable[[], Any]
# (user id, float32 mono 24 kHz samples): every user's audio, before the
# synchronizer picks one speaker.
AudioTap = Callable[[int, np.ndarray], None]


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


class VoiceCapture(voice_recv.AudioSink):
    def __init__(
        self,
        synchronizer: SpeakerSynchronizer,
        *,
        dave_session: DaveSessionGetter = lambda: None,
        decoder_factory: Callable[[], Any] = Decoder,
        tap: AudioTap | None = None,
    ) -> None:
        super().__init__()
        self._synchronizer = synchronizer
        self._dave_session = dave_session
        self._decoder_factory = decoder_factory
        self._tap = tap
        self._decoders: dict[int, Any] = {}

        # What happened to the packets heard so far: the first thing to
        # read when voice misbehaves (see stats()).
        self.counters: Counter[str] = Counter()

    def stats(self) -> str:
        return ", ".join(
            f"{name}={self.counters[name]}"
            for name in (
                "packets",
                "unencrypted",
                "dave_decrypted",
                "dave_passthrough",
                "dave_failed",
                "decode_failed",
            )
        )

    def wants_opus(self) -> bool:
        return True

    def write(self, user, data) -> None:
        if user is None or getattr(user, "bot", False):
            return

        opus = data.opus
        if not opus:
            return

        self.counters["packets"] += 1

        if not isinstance(data.packet, FakePacket):
            opus = self._undo_dave(user.id, opus)
            if opus is None:
                return

        decoder = self._decoders.get(user.id)
        if decoder is None:
            decoder = self._decoders[user.id] = self._decoder_factory()

        try:
            pcm = decoder.decode(opus, fec=False)
        except Exception:
            self.counters["decode_failed"] += 1
            logger.debug("Dropping an undecodable packet from %s", user.id)
            return

        samples = np.frombuffer(discord_audio_to_server(pcm), dtype="<f4")
        if self._tap is not None:
            self._tap(user.id, samples)

        self._synchronizer.push(user.id, samples, _now_ms())

    def _undo_dave(self, user_id: int, opus: bytes) -> bytes | None:
        session = self._dave_session()
        if session is None or not getattr(session, "ready", False):
            self.counters["unencrypted"] += 1
            return opus

        try:
            frame = session.decrypt(user_id, DAVE_AUDIO, opus)
        except Exception:
            # During a DAVE transition a sender may still be unencrypted.
            if session.can_passthrough(user_id):
                self.counters["dave_passthrough"] += 1
                return opus

            self.counters["dave_failed"] += 1
            logger.debug("Dropping an undecryptable packet from %s", user_id)
            return None

        self.counters["dave_decrypted"] += 1
        return frame

    def forget(self, user_id: int) -> None:
        self._decoders.pop(user_id, None)
        self._synchronizer.forget(user_id)

    def cleanup(self) -> None:
        self._decoders.clear()
