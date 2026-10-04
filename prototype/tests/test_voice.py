"""
The voice pieces with synthetic audio: no Discord connection, no server.
"""

import asyncio
import base64
import struct
from contextlib import suppress

import numpy as np

from mulca_discord.voice.bridge import VoiceBridge
from mulca_discord.voice.capture import VoiceCapture, _now_ms as capture_clock
from mulca_discord.voice.player import (
    FRAME_BYTES,
    AssistantPlayer,
    discord_audio_to_server,
    server_audio_to_discord,
)
from mulca_discord.voice.synchronizer import SpeakerSynchronizer
from mulca_discord.sessions import Scope

LOUD = np.full(480, 0.3, dtype=np.float32)
QUIET = np.zeros(480, dtype=np.float32)


# ----------------------------------------------------------------------
# Synchronizer
# ----------------------------------------------------------------------


def test_the_loud_user_holds_the_floor_and_only_their_audio_goes_up():
    sync = SpeakerSynchronizer()

    sync.push(1, LOUD, now_ms=0)
    sync.push(2, QUIET, now_ms=0)

    speaker, audio = sync.take_frame(now_ms=10)

    assert speaker == 1
    assert audio.size == LOUD.size


def test_a_speaker_keeps_the_floor_through_a_short_pause():
    sync = SpeakerSynchronizer(hang_ms=400)

    sync.push(1, LOUD, now_ms=0)
    sync.take_frame(now_ms=0)
    sync.push(2, LOUD * 2, now_ms=200)

    speaker, _ = sync.take_frame(now_ms=300)
    assert speaker == 1

    speaker, _ = sync.take_frame(now_ms=500)
    assert speaker == 2


def test_nobody_holds_the_floor_after_the_hang_time():
    sync = SpeakerSynchronizer(hang_ms=400)

    sync.push(1, LOUD, now_ms=0)
    sync.take_frame(now_ms=0)

    speaker, audio = sync.take_frame(now_ms=1000)

    assert speaker is None
    assert audio.size == 0


def test_a_user_who_left_loses_the_floor():
    sync = SpeakerSynchronizer()
    sync.push(1, LOUD, now_ms=0)
    sync.take_frame(now_ms=0)

    sync.forget(1)

    assert sync.take_frame(now_ms=10)[0] is None


# ----------------------------------------------------------------------
# Player
# ----------------------------------------------------------------------


def floats(*values: float) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def test_server_audio_becomes_48k_stereo_pcm16_and_back():
    pcm = server_audio_to_discord(floats(*([0.5] * 480)))

    # 480 samples at 24 kHz = 20 ms = 960 stereo frames at 48 kHz.
    assert len(pcm) == 960 * 2 * 2
    assert set(np.frombuffer(pcm, dtype="<i2")) == {16383}

    back = np.frombuffer(discord_audio_to_server(pcm), dtype="<f4")
    assert back.size == 480
    assert np.allclose(back, 0.5, atol=1e-3)


def test_the_player_reports_playback_like_the_unity_pusher():
    player = AssistantPlayer()
    player.enqueue(floats(*([0.1] * 2400)))  # 100 ms

    assert player.is_notifying()

    for _ in range(3):
        assert len(player.read()) == FRAME_BYTES

    assert player.playback_time_ms() == 60

    while player.read():
        pass

    # Ran dry: this stretch of playback is over, and the clock restarts.
    assert not player.is_notifying()
    assert player.playback_time_ms() == 0


def test_clearing_the_player_silences_it_at_once():
    player = AssistantPlayer()
    player.enqueue(floats(*([0.1] * 2400)))

    player.clear()

    assert player.read() == b""
    assert not player.is_notifying()


def test_what_was_played_can_be_echoed_to_the_server():
    player = AssistantPlayer()
    player.enqueue(floats(*([0.25] * 480)))
    player.read()

    played = np.frombuffer(player.take_played(), dtype="<f4")

    assert played.size == 480
    assert np.allclose(played, 0.25, atol=1e-3)
    assert player.take_played() == b""


# ----------------------------------------------------------------------
# Capture (with DAVE)
# ----------------------------------------------------------------------


class FakeDecoder:
    def decode(self, data: bytes, *, fec: bool = False) -> bytes:
        # 20 ms of 48 kHz stereo at a fixed level, tagged by the payload.
        level = 8000 if data == b"clear-opus" else 0
        return struct.pack("<1920h", *([level] * 1920))


class FakeDave:
    ready = True

    def __init__(self) -> None:
        self.decrypted: list[int] = []

    def decrypt(self, user_id, media_type, packet):
        self.decrypted.append(user_id)
        assert packet == b"e2ee-opus"
        return b"clear-opus"

    def can_passthrough(self, user_id) -> bool:
        return False


class User:
    def __init__(self, user_id: int, bot: bool = False) -> None:
        self.id = user_id
        self.bot = bot


class Packet:
    pass


class Data:
    def __init__(self, opus: bytes) -> None:
        self.opus = opus
        self.packet = Packet()


def make_capture(dave=None):
    sync = SpeakerSynchronizer()
    capture = VoiceCapture(
        sync,
        dave_session=lambda: dave,
        decoder_factory=FakeDecoder,
    )
    return capture, sync


def test_end_to_end_encrypted_voice_is_decrypted_before_decoding():
    dave = FakeDave()
    capture, sync = make_capture(dave)

    capture.write(User(5), Data(b"e2ee-opus"))

    speaker, audio = sync.take_frame(now_ms=capture_clock())
    assert dave.decrypted == [5]
    assert audio.size == 480
    assert np.allclose(audio, 8000 / 32767, atol=1e-3)


def test_unencrypted_voice_is_decoded_as_is():
    capture, sync = make_capture(dave=None)

    capture.write(User(5), Data(b"clear-opus"))

    _, audio = sync.take_frame(now_ms=capture_clock())
    assert audio.size == 480


def test_bots_are_not_listened_to():
    capture, sync = make_capture()

    capture.write(User(9, bot=True), Data(b"clear-opus"))

    assert sync.take_frame(now_ms=capture_clock())[1].size == 0


# ----------------------------------------------------------------------
# Bridge
# ----------------------------------------------------------------------


class FakeClient:
    def __init__(self) -> None:
        self.frames: list[dict] = []
        self.played: list[str] = []
        self.rosters: list[dict] = []

    async def send_audio_stream(self, **frame) -> None:
        self.frames.append(frame)

    async def send_playback_frame(self, audio: str) -> None:
        self.played.append(audio)

    async def send_participants(self, roster) -> None:
        self.rosters.append(roster)


class FakeSession:
    on_state_update = None


class FakeRegistry:
    def __init__(self) -> None:
        self.client = FakeClient()
        self.session = FakeSession()
        self.closed: list[str] = []

    async def run(self, scope, action, **kwargs):
        await action(self.client)
        return self.session

    async def close(self, conversation_id, **kwargs):
        self.closed.append(conversation_id)
        return True


class FakeVoiceClient:
    def __init__(self) -> None:
        self.playing = False
        self.plays = 0
        self.stops = 0
        self.stops_playing = 0

    def listen(self, sink) -> None:
        pass

    def is_connected(self) -> bool:
        return True

    def is_playing(self) -> bool:
        return self.playing

    def play(self, source) -> None:
        self.plays += 1
        self.playing = True

    def stop_playing(self) -> None:
        # Real VoiceRecvClient.stop() also tears down voice *receiving*
        # (stop_listening) -- a distinct method, since a barge-in should
        # only ever stop outgoing playback, never receiving.
        self.stops_playing += 1
        self.playing = False

    def stop(self) -> None:
        self.stops += 1
        self.playing = False


def make_bridge(*, on_unhealthy=None):
    registry = FakeRegistry()
    voice = FakeVoiceClient()
    bridge = VoiceBridge(
        scope=Scope(conversation_id="instance:team-alpha"),
        registry=registry,
        voice_client=voice,
        reply_channel=None,
        roster=lambda: {1: "Ada"},
        on_unhealthy=on_unhealthy,
    )
    return bridge, registry, voice


async def test_every_tick_sends_a_frame_even_when_nobody_speaks():
    bridge, registry, _ = make_bridge()

    await bridge._tick()

    assert registry.client.frames == [
        {
            "speaker": None,
            "audio": "",
            "is_notifying": False,
            "playback_time_ms": 0,
        }
    ]


async def test_the_speakers_audio_goes_up_with_their_id():
    bridge, registry, _ = make_bridge()
    bridge.synchronizer.push(1, LOUD, now_ms=10**12)

    import mulca_discord.voice.bridge as bridge_module

    bridge_module_now = bridge_module._now_ms
    bridge_module._now_ms = lambda: 10**12
    try:
        await bridge._tick()
    finally:
        bridge_module._now_ms = bridge_module_now

    frame = registry.client.frames[-1]
    assert frame["speaker"] == 1
    assert len(base64.b64decode(frame["audio"])) == LOUD.size * 4
    # A newcomer to the floor gets their name sent first.
    assert registry.client.rosters[-1] == {1: "Ada"}


async def test_spoken_replies_play_and_a_clear_silences_them():
    """
    clearAudioQueue (a barge-in) must only stop playback, never receiving:
    VoiceRecvClient.stop() stops both and tears down the receive sink
    permanently (nothing ever calls listen() again) -- confirmed live, this
    silently and permanently killed voice input the moment anyone first
    interrupted MULCA.
    """

    bridge, registry, voice = make_bridge()
    await bridge._tick()
    handler = registry.session.on_state_update

    audio = base64.b64encode(floats(*([0.1] * 2400))).decode()
    await handler({"event": "state_update", "audio": audio})

    assert voice.plays == 1
    assert bridge.player.is_notifying()

    await handler({"event": "state_update", "audio": "", "clearAudioQueue": True})

    assert voice.stops_playing == 1
    assert voice.stops == 0
    assert not bridge.player.is_notifying()


# ----------------------------------------------------------------------
# Watchdog
# ----------------------------------------------------------------------


class AlwaysFailingRegistry(FakeRegistry):
    """A registry whose session is unreachable no matter what -- tier 1
    (reopening the session) can never verifiably fix anything here, so a
    failing bridge should always escalate to tier 2."""

    async def run(self, scope, action, **kwargs):
        raise RuntimeError("still down")


async def test_one_or_two_failed_ticks_do_not_trigger_recovery():
    recovered = []
    bridge, registry, _ = make_bridge(on_unhealthy=lambda: recovered.append(1))

    await bridge._watchdog_tick_failed()
    await bridge._watchdog_tick_failed()

    assert registry.closed == []
    assert recovered == []


async def test_three_consecutive_failures_reopen_the_session_and_stop_there():
    recovered = []
    bridge, registry, _ = make_bridge(on_unhealthy=lambda: recovered.append(1))

    await bridge._watchdog_tick_failed()
    await bridge._watchdog_tick_failed()
    await bridge._watchdog_tick_failed()

    # Tier 1: the fake registry's session works again right away, so there
    # is nothing left for tier 2 to do.
    assert registry.closed == ["instance:team-alpha"]
    assert recovered == []
    assert bridge._consecutive_tick_failures == 0


async def test_a_tier_1_failure_escalates_to_tier_2():
    async def recover():
        recovered.append(1)

    recovered = []
    bridge, _, _ = make_bridge(on_unhealthy=recover)
    bridge._registry = AlwaysFailingRegistry()

    await bridge._watchdog_tick_failed()
    await bridge._watchdog_tick_failed()
    await bridge._watchdog_tick_failed()
    # Tier 2 is scheduled as its own task, not awaited in place (it may
    # need to cancel the very task _watchdog_tick_failed runs inside of).
    await asyncio.sleep(0)

    assert bridge._registry.closed == ["instance:team-alpha"]
    assert recovered == [1]


async def test_a_dead_tick_loop_goes_straight_to_tier_2():
    async def recover():
        recovered.append(1)

    recovered = []
    bridge, _, _ = make_bridge(on_unhealthy=recover)

    async def boom() -> None:
        raise RuntimeError("the tick loop itself crashed")

    task = asyncio.create_task(boom())
    with suppress(RuntimeError):
        await task

    bridge._report_if_run_died(task)
    await asyncio.sleep(0)

    assert recovered == [1]


# ----------------------------------------------------------------------
# Diagnostics
# ----------------------------------------------------------------------


class FailingDave(FakeDave):
    def decrypt(self, user_id, media_type, packet):
        raise ValueError("no key")


def test_the_capture_counts_what_happened_to_each_packet():
    capture, _ = make_capture(FakeDave())
    capture.write(User(5), Data(b"e2ee-opus"))

    unencrypted, _ = make_capture(dave=None)
    unencrypted.write(User(5), Data(b"clear-opus"))

    failing, _ = make_capture(FailingDave())
    failing.write(User(5), Data(b"e2ee-opus"))

    assert capture.counters["packets"] == 1
    assert capture.counters["dave_decrypted"] == 1
    assert unencrypted.counters["unencrypted"] == 1
    assert failing.counters["dave_failed"] == 1
    assert "dave_failed=1" in failing.stats()


class _BorrowConflict(BaseException):
    """
    Stands in for a davey (Rust, via PyO3) panic: not guaranteed to be an
    Exception subclass, unlike an ordinary decrypt failure (ValueError
    above). A bare `except Exception` would let this escape and kill the
    whole sink's receive thread; `_undo_dave` must catch it too.
    """


class PanickingDave(FakeDave):
    def decrypt(self, user_id, media_type, packet):
        raise _BorrowConflict("davey: already borrowed")


def test_a_non_exception_decrypt_failure_is_dropped_not_fatal():
    dave = PanickingDave()
    capture, _ = make_capture(dave)

    # Would propagate out of write() and kill this sink's thread if
    # _undo_dave only caught Exception, not BaseException.
    capture.write(User(5), Data(b"e2ee-opus"))

    assert capture.counters["dave_failed"] == 1


def test_the_tap_hears_every_user_not_just_the_floor():
    heard = []
    capture = VoiceCapture(
        SpeakerSynchronizer(),
        decoder_factory=FakeDecoder,
        tap=lambda user_id, samples: heard.append((user_id, samples.size)),
    )

    capture.write(User(5), Data(b"clear-opus"))
    capture.write(User(6), Data(b"clear-opus"))

    assert heard == [(5, 480), (6, 480)]


def test_the_upstream_recording_is_a_valid_wav_on_a_real_timeline(tmp_path):
    import wave

    from mulca_discord.voice.debug import UpstreamRecorder

    recorder = UpstreamRecorder(tmp_path, "instance_x")
    recorder.write_tick(1, LOUD, tick_samples=2400)
    recorder.write_tick(None, np.zeros(0, dtype=np.float32), tick_samples=2400)
    recorder.close()

    with wave.open(str(tmp_path / "instance_x.wav")) as wav:
        assert wav.getframerate() == 24_000
        assert wav.getsampwidth() == 2
        assert wav.getnframes() == LOUD.size + 2400

    floor = (tmp_path / "instance_x.floor.txt").read_text(encoding="utf-8")
    assert "floor: 1" in floor
    assert "floor: (nobody)" in floor


async def test_the_bridge_records_what_it_sends_when_asked(tmp_path, monkeypatch):
    monkeypatch.setenv("MULCA_VOICE_DEBUG_DIR", str(tmp_path))
    bridge, registry, _ = make_bridge()

    await bridge.start()
    await bridge._tick()
    await bridge.stop()

    assert list(tmp_path.glob("instance_team-alpha-*.wav"))
