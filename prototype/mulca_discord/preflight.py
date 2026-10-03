"""
Checks everything the bot needs before a real run, one PASS/FAIL line each.

    python -m mulca_discord.preflight
    python -m mulca_discord.preflight --voice-test 10

- the voice libraries (opus, PyNaCl, davey) load;
- the instances file (MULCA_INSTANCES, or the default) parses;
- MUCA-Server answers a handshake;
- the bot token logs in, with the privileged intents enabled;
- every configured channel exists and the bot may use it.

--voice-test N also joins the first instance's voice channel and records
every user separately for N seconds -- no MUCA-Server involved -- to
voice-test/<user id>.wav, and prints what happened to the packets. Talk
while it runs, then listen: if that is not clearly your voice, the problem
is receiving (or DAVE decryption), not anything downstream.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
import numpy as np
from dotenv import load_dotenv

from .discord_client import mulca_intents
from .instances import MulcaInstance, configured_instances_path, load_instances
from .muca_client import MucaWsClient
from .permissions import missing_permissions
from .voice.debug import WavRecorder

VOICE_TEST_DIR = Path("voice-test")


class Report:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, ok: bool, name: str, detail: str = "") -> bool:
        print(f"{'PASS' if ok else 'FAIL'}  {name}{f' -- {detail}' if detail else ''}")
        if not ok:
            self.failed += 1
        return ok

    def note(self, text: str) -> None:
        print(f"      {text}")


def check_voice_libraries(report: Report) -> None:
    import discord.opus

    try:
        discord.opus._load_default()
    except Exception as exc:
        report.check(False, "opus loads", str(exc))
    else:
        report.check(discord.opus.is_loaded(), "opus loads")

    for module, why in (
        ("nacl", "PyNaCl, voice transport"),
        ("davey", "DAVE end-to-end voice encryption"),
        ("discord.ext.voice_recv", "per-user voice receive"),
    ):
        try:
            __import__(module)
        except ImportError as exc:
            report.check(False, f"{module} imports ({why})", str(exc))
        else:
            report.check(True, f"{module} imports ({why})")


def check_instances(report: Report) -> list[MulcaInstance]:
    path = configured_instances_path()
    try:
        instances = load_instances(path)
    except Exception as exc:
        report.check(False, f"instances file {path}", str(exc))
        return []

    report.check(
        bool(instances),
        f"instances file {path}",
        ", ".join(instance.name for instance in instances) or "no instances",
    )
    return instances


async def check_muca_server(report: Report, url: str) -> None:
    # No conversation id: an ephemeral session, nothing persisted for it.
    client = MucaWsClient(url, conversation_id="", is_dm=False)

    try:
        await asyncio.wait_for(client.connect(), timeout=10)
        for _ in range(100):
            if client.agent_guids:
                break
            await asyncio.sleep(0.1)
    except Exception as exc:
        report.check(False, f"MUCA-Server at {url}", str(exc) or type(exc).__name__)
        return
    finally:
        await client.close()

    report.check(
        bool(client.agent_guids),
        f"MUCA-Server at {url}",
        "handshake and intervention agent OK"
        if client.agent_guids
        else "connected, but no agent_guid came back (see the server's log)",
    )


def check_channels(
    report: Report,
    client: discord.Client,
    instances: list[MulcaInstance],
) -> None:
    for instance in instances:
        text = client.get_channel(instance.text_channel_id)
        if report.check(
            text is not None,
            f"{instance.name}: text channel {instance.text_channel_id}",
            f"#{text}" if text else "not visible to the bot (wrong id, or not invited?)",
        ):
            missing = missing_permissions(text, text.guild.me, voice=False)
            report.check(
                not missing,
                f"{instance.name}: may post in #{text}",
                f"missing {missing}" if missing else "",
            )

            humans = [m for m in getattr(text, "members", []) if not m.bot]
            report.check(
                bool(humans),
                f"{instance.name}: sees members of #{text}",
                f"{len(humans)} people"
                if humans
                else "none -- is the Server Members Intent enabled?",
            )

        if instance.voice_channel_id is None:
            report.note(f"{instance.name}: no voice channel configured")
            continue

        voice = client.get_channel(instance.voice_channel_id)
        if report.check(
            isinstance(voice, discord.VoiceChannel),
            f"{instance.name}: voice channel {instance.voice_channel_id}",
            f"{voice}" if voice else "not visible to the bot",
        ):
            missing = missing_permissions(voice, voice.guild.me, voice=True)
            report.check(
                not missing,
                f"{instance.name}: may talk in {voice}",
                f"missing {missing}" if missing else "",
            )


async def voice_test(
    report: Report,
    client: discord.Client,
    instance: MulcaInstance,
    seconds: int,
) -> None:
    from discord.ext import voice_recv

    from .voice.capture import VoiceCapture
    from .voice.synchronizer import SpeakerSynchronizer

    channel = client.get_channel(instance.voice_channel_id)
    if channel is None:
        report.check(False, "voice test", "voice channel not visible")
        return

    heard: dict[int, list[np.ndarray]] = {}

    def tap(user_id: int, samples: np.ndarray) -> None:
        heard.setdefault(user_id, []).append(samples)

    try:
        voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
    except Exception as exc:
        report.check(False, f"joins {channel}", str(exc) or type(exc).__name__)
        return

    report.check(True, f"joins {channel}")

    connection = getattr(voice_client, "_connection", None)
    report.note(
        "DAVE protocol version "
        f"{getattr(connection, 'dave_protocol_version', '?')} "
        "(0 means the channel is not end-to-end encrypted)"
    )

    capture = VoiceCapture(
        SpeakerSynchronizer(),
        dave_session=lambda: getattr(connection, "dave_session", None),
        tap=tap,
    )
    voice_client.listen(capture)

    print(f"      recording for {seconds} s -- talk now...")
    await asyncio.sleep(seconds)

    voice_client.stop_listening()
    await voice_client.disconnect(force=True)

    report.note(f"packets: {capture.stats()}")
    report.check(
        capture.counters["packets"] > 0,
        "received voice packets",
        "" if capture.counters["packets"] else "none -- did anyone talk?",
    )
    report.check(
        capture.counters["dave_failed"] == 0,
        "no packet failed DAVE decryption",
        f"{capture.counters['dave_failed']} failed"
        if capture.counters["dave_failed"]
        else "",
    )

    for user_id, chunks in heard.items():
        samples = np.concatenate(chunks)
        recorder = WavRecorder(VOICE_TEST_DIR / f"{user_id}.wav")
        recorder.write(samples)
        recorder.close()

        member = channel.guild.get_member(user_id)
        rms = float(np.sqrt(np.mean(np.square(samples))))
        report.note(
            f"{member.display_name if member else user_id}: "
            f"{recorder.seconds:.1f} s, rms {rms:.3f} -> {recorder.path}"
        )

    if heard:
        report.note("listen to those files: they should sound like you")


async def run(voice_test_seconds: int | None) -> int:
    load_dotenv()
    logging.basicConfig(level=logging.WARNING)
    report = Report()

    check_voice_libraries(report)
    instances = check_instances(report)
    await check_muca_server(
        report,
        os.environ.get("MUCA_SERVER_URL", "ws://localhost:8000/"),
    )

    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not report.check(bool(token), "DISCORD_BOT_TOKEN is set"):
        return 1

    client = discord.Client(intents=mulca_intents())

    @client.event
    async def on_ready() -> None:
        try:
            report.check(True, f"logs in as {client.user}")
            check_channels(report, client, instances)

            if voice_test_seconds:
                with_voice = [i for i in instances if i.voice_channel_id]
                if with_voice:
                    await voice_test(
                        report,
                        client,
                        with_voice[0],
                        voice_test_seconds,
                    )
                else:
                    report.check(False, "voice test", "no instance has a voice channel")
        finally:
            await client.close()

    try:
        async with client:
            await client.start(token)
    except discord.LoginFailure:
        report.check(False, "logs in", "the token was rejected")
    except discord.PrivilegedIntentsRequired:
        report.check(
            False,
            "logs in",
            "enable the Message Content and Server Members intents in the "
            "developer portal (Bot page)",
        )

    print()
    print("all checks passed" if not report.failed else f"{report.failed} check(s) failed")
    return 1 if report.failed else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check the bot's setup before a real run.",
    )
    parser.add_argument(
        "--voice-test",
        type=int,
        metavar="SECONDS",
        help="also record the first voice channel for this long",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(run(args.voice_test)))


if __name__ == "__main__":
    main()
