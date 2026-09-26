"""
Plays MULCA's spoken replies into the voice channel.

A port of the Unity package's AssistantAudioPusher: the server's audio (float32
mono at 24 kHz) is queued as it arrives and played at real time. What the
client reports back -- whether it is still playing (`is_notifying`) and how
far into the current stretch of playback it is (`playback_time_ms`) -- is
what MUCA-Server's turn taking and truncation run on, so the semantics
match the Unity client's exactly.

discord.py pulls frames from `read()` on its own audio thread, 20 ms at a
time, as 48 kHz stereo PCM16.
"""

from __future__ import annotations

import threading
from collections import deque

import discord
import numpy as np

from muca_server.audio.pcm import float32_to_pcm16, resample

SERVER_RATE = 24_000
DISCORD_RATE = 48_000

# One discord.py frame: 20 ms of 48 kHz stereo 16-bit audio.
FRAME_SAMPLES = DISCORD_RATE // 50
FRAME_BYTES = FRAME_SAMPLES * 2 * 2


def server_audio_to_discord(data: bytes) -> bytes:
    """float32 mono 24 kHz -> PCM16 stereo 48 kHz."""

    mono = np.frombuffer(data[: len(data) - len(data) % 4], dtype="<f4")
    upsampled = resample(mono, SERVER_RATE, DISCORD_RATE)
    stereo = np.repeat(upsampled, 2)

    return float32_to_pcm16(stereo.astype("<f4").tobytes())


def discord_audio_to_server(frame: bytes) -> bytes:
    """PCM16 stereo 48 kHz -> float32 mono 24 kHz."""

    samples = np.frombuffer(frame[: len(frame) - len(frame) % 4], dtype="<i2")
    mono = samples.reshape(-1, 2).mean(axis=1) / 32767.0

    # 48 -> 24 kHz: average each pair, a cheap low-pass and decimation.
    usable = mono.size - mono.size % 2
    downsampled = mono[:usable].reshape(-1, 2).mean(axis=1)

    return downsampled.astype("<f4").tobytes()


class AssistantPlayer(discord.AudioSource):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue = bytearray()

        # 48 kHz samples played since the current stretch of playback began;
        # reset whenever the queue runs dry (AssistantAudioPusher.cs does the
        # same), so it tracks the reply being played, not all time.
        self._consumed_samples = 0

        # What was played, for the observers (sent as playback_frame).
        self._played: deque[bytes] = deque()

    # -- fed from the asyncio loop ------------------------------------

    def enqueue(self, server_audio: bytes) -> None:
        pcm = server_audio_to_discord(server_audio)
        with self._lock:
            self._queue.extend(pcm)

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
            self._consumed_samples = 0

    def is_notifying(self) -> bool:
        """Still playing: more than one frame queued."""

        with self._lock:
            return len(self._queue) > FRAME_BYTES

    def playback_time_ms(self) -> int:
        with self._lock:
            return self._consumed_samples * 1000 // DISCORD_RATE

    def take_played(self) -> bytes:
        """Everything played since the last call, as server audio."""

        with self._lock:
            frames = list(self._played)
            self._played.clear()

        return b"".join(discord_audio_to_server(frame) for frame in frames)

    # -- discord.AudioSource, on discord.py's audio thread ------------

    def read(self) -> bytes:
        with self._lock:
            if not self._queue:
                # Ran dry: playback of this stretch is over. Returning
                # nothing ends the player; the next reply restarts it.
                self._consumed_samples = 0
                return b""

            frame = bytes(self._queue[:FRAME_BYTES])
            del self._queue[:FRAME_BYTES]

            if len(frame) < FRAME_BYTES:
                frame += bytes(FRAME_BYTES - len(frame))

            self._consumed_samples += FRAME_SAMPLES
            self._played.append(frame)

            return frame

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        # Reused across replies: nothing to release when one ends.
        pass
