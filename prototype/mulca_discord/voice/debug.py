"""
Voice debugging aids: record audio to WAV files, to hear what went where.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 24_000


class WavRecorder:
    """Appends float32 mono 24 kHz audio to a 16-bit PCM WAV file."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._file = wave.open(str(path), "wb")
        self._file.setnchannels(1)
        self._file.setsampwidth(2)
        self._file.setframerate(SAMPLE_RATE)
        self.samples_written = 0

    def write(self, samples: np.ndarray) -> None:
        if samples.size == 0:
            return

        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
        self._file.writeframes(pcm.tobytes())
        self.samples_written += samples.size

    @property
    def seconds(self) -> float:
        return self.samples_written / SAMPLE_RATE

    def close(self) -> None:
        self._file.close()


class UpstreamRecorder:
    """
    Exactly what MUCA-Server hears from a voice channel: one WAV of the
    audio_stream frames as sent (silence while nobody holds the floor, so
    the timeline is real), and a text log of who held the floor when.
    """

    def __init__(self, directory: Path, name: str) -> None:
        self.audio = WavRecorder(directory / f"{name}.wav")
        self._floor_log = (directory / f"{name}.floor.txt").open(
            "w",
            encoding="utf-8",
        )
        self._speaker: int | None = None

    def write_tick(
        self,
        speaker: int | None,
        samples: np.ndarray,
        tick_samples: int,
    ) -> None:
        if speaker != self._speaker:
            self._floor_log.write(
                f"{self.audio.seconds:8.2f}s  floor: "
                f"{speaker if speaker is not None else '(nobody)'}\n",
            )
            self._floor_log.flush()
            self._speaker = speaker

        self.audio.write(
            samples
            if samples.size
            else np.zeros(tick_samples, dtype=np.float32),
        )

    def close(self) -> None:
        self.audio.close()
        self._floor_log.close()
