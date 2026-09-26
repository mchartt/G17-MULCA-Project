"""
MULCA's side of the wire, against a real MUCA-Server app served in-process.

The server runs the real session runtime and Conversation, with a scripted
main agent in place of OpenAI -- so these check the actual protocol both
repositories speak, not a copy of it.
"""

import asyncio
import socket

import pytest
import uvicorn

from muca_server import create_app
from muca_server.agents import AuxiliaryAgent, MainAgent
from muca_server.sessions import DefaultSessionComponentsFactory

from mulca_discord.muca_client import MucaConnectionLost, MucaWsClient
from mulca_discord.sessions import Scope, SessionRegistry


class EchoMainAgent(MainAgent):
    """Replies to every instruction with the last thing it was told."""

    heard: list[str] = []

    async def _send_text(self, text: str, *, role: str) -> None:
        if role == "user":
            EchoMainAgent.heard.append(text)

    async def _trigger_response(self, **kwargs) -> None:
        await self._stream_text("echo: ")
        await self._stream_text(EchoMainAgent.heard[-1])
        await self._stream_text("", is_final=True)


class Factory:
    def build_main(self, options):
        return EchoMainAgent(options=options)

    def build_auxiliary(self, options):
        return AuxiliaryAgent(options=options)


class AnswerEverything:
    """Cognition that answers every utterance, and records the handshake."""

    seen: list[tuple[str, bool, str | None]] = []

    async def start(self, port) -> None:
        self._port = port
        AnswerEverything.seen.append(
            (port.conversation_id, port.is_private, port.linked_conversation_id)
        )

    async def close(self) -> None:
        pass

    async def on_utterance(self, utterance) -> bool:
        await self._port.instruct_main_agent("answer")
        return False

    async def on_intervention_signal(self, agent_guid, signal) -> None:
        pass

    async def on_assistant_output(self, text, *, interrupted) -> None:
        pass

    async def wait_for_turn_to_finish(self) -> None:
        pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Server:
    def __init__(self, port: int) -> None:
        self.port = port
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task | None = None

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/"

    async def start(self) -> None:
        app = create_app(
            components_factory=DefaultSessionComponentsFactory(
                agent_factory=Factory(),
                policy_factory=lambda context: AnswerEverything(),
            )
        )
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        )
        self._task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            await asyncio.sleep(0.01)

    async def stop(self) -> None:
        assert self._server is not None and self._task is not None
        self._server.should_exit = True
        self._server.force_exit = True
        await self._task


@pytest.fixture
async def server():
    EchoMainAgent.heard = []
    AnswerEverything.seen = []
    running = Server(free_port())
    await running.start()
    yield running
    await running.stop()


async def collect_reply(client: MucaWsClient) -> list[tuple[str, bool, str]]:
    frames: list[tuple[str, bool, str]] = []
    done = asyncio.Event()

    async def on_text(text, is_final, modality) -> None:
        frames.append((text, is_final, modality))
        if is_final:
            done.set()

    client.on_assistant_text = on_text
    return frames, done


async def test_the_handshake_carries_the_scope_and_a_reply_streams_back(server):
    client = MucaWsClient(
        server.url,
        conversation_id="dm:42",
        is_dm=True,
        linked_conversation_id="instance:team-alpha",
    )
    frames, done = await collect_reply(client)
    await client.connect()

    await client.send_user_text(speaker=42, speaker_name="Ada", text="hello")
    await asyncio.wait_for(done.wait(), timeout=5)
    await client.close()

    assert AnswerEverything.seen == [("dm:42", True, "instance:team-alpha")]
    assert "".join(text for text, _, _ in frames) == "echo: Ada: hello"
    assert frames[-1][1:] == (True, "text")


async def test_a_lost_server_is_noticed_and_sending_says_so(server):
    client = MucaWsClient(server.url, conversation_id="instance:a", is_dm=False)
    closed = asyncio.Event()

    async def on_closed() -> None:
        closed.set()

    client.on_closed = on_closed
    await client.connect()

    await server.stop()
    await asyncio.wait_for(closed.wait(), timeout=5)

    assert not client.is_open
    with pytest.raises(MucaConnectionLost):
        await client.send_user_text(speaker=1, speaker_name="Ada", text="hi")

    # The fixture stops it again; give it something to stop.
    await server.start()


async def test_the_registry_reopens_a_scope_after_a_server_restart(server):
    replies: list[str] = []

    class Channel:
        async def send(self, content):
            replies.append(content)

            class Message:
                def __init__(self, text):
                    self.content = text

                async def edit(self, content):
                    replies.append(content)
                    self.content = content

            return Message(content)

    registry = SessionRegistry(server.url, reconnect_delays=(0.0, 0.2, 0.5, 1.0))
    scope = Scope(conversation_id="instance:team-alpha")
    channel = Channel()

    async def say(text):
        async def send(client):
            await client.send_user_text(speaker=1, speaker_name="Ada", text=text)

        await registry.run(scope, send, reply_channel=channel)

    await say("first")
    first = registry.find(scope.conversation_id).client
    await asyncio.sleep(0.3)

    await server.stop()
    await asyncio.sleep(0.2)
    await server.start()

    await say("second")
    await asyncio.sleep(0.3)
    await registry.close_all()

    assert registry.find(scope.conversation_id) is None
    assert not first.is_open
    assert any("first" in reply for reply in replies)
    assert any("second" in reply for reply in replies)
    assert [seen[0] for seen in AnswerEverything.seen] == [
        "instance:team-alpha",
        "instance:team-alpha",
    ]


async def test_voice_frames_are_accepted_and_state_updates_come_back(server):
    client = MucaWsClient(server.url, conversation_id="instance:v", is_dm=False)
    updates: list[dict] = []

    async def on_state(data) -> None:
        updates.append(data)

    client.on_state_update = on_state
    await client.connect()

    import base64
    import struct

    voice = base64.b64encode(struct.pack("<480f", *([0.2] * 480))).decode()
    await client.send_audio_stream(
        speaker=7,
        audio=voice,
        is_notifying=False,
        playback_time_ms=0,
    )
    await client.send_audio_stream(
        speaker=None,
        audio="",
        is_notifying=False,
        playback_time_ms=0,
    )
    await client.send_playback_frame(voice)
    await asyncio.sleep(0.3)
    await client.close()

    speakers = [update["currentSpeaker"] for update in updates]
    assert 7 in speakers
    assert speakers[-1] == -1
