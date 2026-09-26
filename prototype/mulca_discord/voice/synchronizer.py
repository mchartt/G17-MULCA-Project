"""
Who holds the floor in the voice channel, and what they said this tick.

A port of the Unity package's UserAudioSynchronizerBasic: every user's audio
is buffered as it arrives, and once per tick the current speaker's audio is
handed on, alone. MUCA-Server assumes one speaker at a time, so everybody
else's audio for that tick is dropped. A speaker keeps the floor through
short pauses (the hang time), so a breath is not a turn change.

Thread-safe: audio is pushed from the voice receive thread and taken from
the asyncio loop.
"""

from __future__ import annotations

import threading
from collections import deque

import numpy as np

SAMPLE_RATE = 24_000

# Mean-square energy, of float samples in [-1, 1], above which a user counts
# as speaking. Discord clients already stop sending when their own voice
# activity detection hears nothing, so this mostly filters out breaths.
DEFAULT_ENERGY_THRESHOLD = 1e-4

# How long a speaker keeps the floor after their last loud frame.
DEFAULT_HANG_MS = 400

# Audio buffered per user is capped, in case nobody takes it.
MAX_BUFFERED_SAMPLES = 2 * SAMPLE_RATE


class SpeakerSynchronizer:
    def __init__(
        self,
        *,
        energy_threshold: float = DEFAULT_ENERGY_THRESHOLD,
        hang_ms: int = DEFAULT_HANG_MS,
    ) -> None:
        self._energy_threshold = energy_threshold
        self._hang_ms = hang_ms

        self._lock = threading.Lock()
        self._buffers: dict[int, deque[np.ndarray]] = {}
        self._buffered: dict[int, int] = {}
        self._last_loud_ms: dict[int, int] = {}
        self._energy: dict[int, float] = {}
        self._current: int | None = None

    @property
    def current_speaker(self) -> int | None:
        return self._current

    def push(self, user_id: int, samples: np.ndarray, now_ms: int) -> None:
        """One user's audio, float32 mono at 24 kHz, as it arrives."""

        if samples.size == 0:
            return

        energy = float(np.mean(np.square(samples, dtype=np.float64)))

        with self._lock:
            buffer = self._buffers.setdefault(user_id, deque())
            buffer.append(samples)
            self._buffered[user_id] = (
                self._buffered.get(user_id, 0) + samples.size
            )

            while self._buffered[user_id] > MAX_BUFFERED_SAMPLES:
                dropped = buffer.popleft()
                self._buffered[user_id] -= dropped.size

            if energy >= self._energy_threshold:
                self._last_loud_ms[user_id] = now_ms
                self._energy[user_id] = energy

    def take_frame(self, now_ms: int) -> tuple[int | None, np.ndarray]:
        """
        The current speaker and their audio since the last call (empty when
        nobody holds the floor). Everyone else's audio is discarded.
        """

        with self._lock:
            holding = {
                user_id
                for user_id, loud_ms in self._last_loud_ms.items()
                if now_ms - loud_ms <= self._hang_ms
            }

            if self._current not in holding:
                # The floor goes to whoever is loudest right now.
                self._current = max(
                    holding,
                    key=lambda user_id: self._energy.get(user_id, 0.0),
                    default=None,
                )

            audio = (
                np.concatenate(list(self._buffers[self._current]))
                if self._current is not None and self._buffers.get(self._current)
                else np.zeros(0, dtype=np.float32)
            )

            for buffer in self._buffers.values():
                buffer.clear()
            self._buffered = dict.fromkeys(self._buffered, 0)

            return self._current, audio.astype(np.float32, copy=False)

    def forget(self, user_id: int) -> None:
        """A user left the channel."""

        with self._lock:
            self._buffers.pop(user_id, None)
            self._buffered.pop(user_id, None)
            self._last_loud_ms.pop(user_id, None)
            self._energy.pop(user_id, None)
            if self._current == user_id:
                self._current = None
