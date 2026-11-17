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

from mulca_discord.muca_client import MucaConnectionLost, MucaWsClient, set_server_model
from mulca_discord.sessions import Scope, SessionRegistry


class EchoMainAgent(MainAgent):
    """Replies to every instruction with the last thing it was told."""

    heard: list[str] = []
    sessions: list[dict] = []

    async def _update_session(self, session) -> None:
        EchoMainAgent.sessions.append(session)

    async def _send_text(self, text: str, *, role: str) -> None:
        if role == "user":
            EchoMainAgent.heard.append(text)

    async def _trigger_response(self, **kwargs) -> None:
        if EchoMainAgent.heard[-1].endswith("costly"):
            # What the server's estimator does after each provider call.
            from muca_server.usage_report import usage_sink

            _, send = usage_sink.get()
            await send("main", (10, 20, 30, 40, 50, 60), 0.25)

        if EchoMainAgent.heard[-1].endswith("drop"):
            # As OpenAI does after 60 minutes: the provider connection ends.
            await self._connection_lost("the provider ended the session")
            return

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
    closed: list[str] = []

    async def start(self, port) -> None:
        self._port = port
        AnswerEverything.seen.append(
            (port.conversation_id, port.is_private, port.linked_conversation_id)
        )

    async def close(self) -> None:
        AnswerEverything.closed.append(self._port.conversation_id)

    def observer_catchup_text(self) -> str:
        # Asked by MUCA-Server since the Catch up of linked channels; nothing to catch up here.
        return ""

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
    AnswerEverything.closed = []
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
    EchoMainAgent.sessions = []
    await client.connect()

    await client.send_user_text(speaker=42, speaker_name="Ada", text="hello")
    await asyncio.wait_for(done.wait(), timeout=5)
    await client.close()

    assert AnswerEverything.seen == [("dm:42", True, "instance:team-alpha")]
    # The main agent became the AUI teaching assistant before the first turn.
    [session] = EchoMainAgent.sessions
    assert "Advanced User Interfaces" in session["instructions"]
    assert "".join(text for text, _, _ in frames) == "echo: Ada: hello"
    assert frames[-1][1:] == (True, "text")


async def test_arm_listening_reports_the_real_toggled_state(server):
    client = MucaWsClient(
        server.url,
        conversation_id="channel:1",
        is_dm=False,
        listening_mode="toggle",
    )
    await client.connect()

    assert await client.arm_listening() is True
    assert await client.arm_listening() is False

    await client.close()


async def test_arm_listening_times_out_to_none_in_ambient_mode(server):
    # The fixture's own server defaults to ambient (no listening_mode
    # override sent), where MUCA-Server's arm_listening is a silent no-op
    # -- nothing ever confirms a new state back.
    client = MucaWsClient(server.url, conversation_id="channel:2", is_dm=False)
    await client.connect()

    assert await client.arm_listening(timeout=0.2) is None

    await client.close()


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


class Channel:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def send(self, content):
        self.replies.append(content)
        replies = self.replies

        class Message:
            def __init__(self, text):
                self.content = text

            async def edit(self, content):
                replies.append(content)
                self.content = content

        return Message(content)


async def say(registry, scope, channel, text):
    async def send(client):
        await client.send_user_text(speaker=1, speaker_name="Ada", text=text)

    return await registry.run(scope, send, reply_channel=channel, retry_once=False)


async def test_a_server_that_ends_the_session_gets_it_reopened_on_next_use(server):
    registry = SessionRegistry(server.url)
    scope = Scope(conversation_id="instance:a")
    channel = Channel()

    first = (await say(registry, scope, channel, "drop")).client
    for _ in range(100):
        if not first.is_open:
            break
        await asyncio.sleep(0.05)

    # 1012: MUCA-Server restarted the session on purpose, memory saved.
    assert not first.is_open
    assert first.close_code == 1012
    assert AnswerEverything.closed == ["instance:a"]

    # A text message sent after the close arrived is not dropped: the
    # registry reopens before sending it.
    second = (await say(registry, scope, channel, "still there?")).client
    await asyncio.sleep(0.3)
    await registry.close_all()

    assert second is not first
    assert any("still there?" in reply for reply in channel.replies)
    assert [seen[0] for seen in AnswerEverything.seen] == ["instance:a", "instance:a"]


async def test_a_waiting_close_returns_once_the_server_has_saved(server):
    client = MucaWsClient(server.url, conversation_id="instance:w", is_dm=False)
    await client.connect()
    await asyncio.sleep(0.1)

    confirmed = await client.close(wait_for_server=5)

    assert confirmed
    assert AnswerEverything.closed == ["instance:w"]


async def test_a_restart_opens_a_fresh_session_for_that_scope_only(server):
    registry = SessionRegistry(server.url)
    restarted = Scope(conversation_id="instance:r")
    untouched = Scope(conversation_id="instance:u")
    channel = Channel()

    old = (await say(registry, restarted, channel, "one")).client
    other = (await say(registry, untouched, channel, "two")).client
    await asyncio.sleep(0.2)

    assert await registry.restart(restarted.conversation_id)
    assert not old.is_open
    assert AnswerEverything.closed == ["instance:r"]
    assert other.is_open

    new = (await say(registry, restarted, channel, "three")).client
    await asyncio.sleep(0.2)
    await registry.close_all()

    assert new is not old
    assert [seen[0] for seen in AnswerEverything.seen].count("instance:r") == 2


async def test_restarting_a_scope_with_no_session_is_a_no_op(server):
    registry = SessionRegistry(server.url)

    assert await registry.restart("instance:none")


async def test_the_servers_model_cannot_be_changed_by_a_server_without_an_admin_token(
    server,
):
    problem = await set_server_model(server.url, "secret", "gpt-new")

    assert problem is not None and "not enabled" in problem


async def test_an_unreachable_server_is_reported_not_raised():
    problem = await set_server_model(f"ws://127.0.0.1:{free_port()}/", "secret", "m")

    assert problem is not None and "couldn't reach" in problem


async def test_a_server_that_refuses_the_session_is_not_taken_for_open(server, monkeypatch):
    from muca_server.sessions.session_runtime import SessionRuntime

    # MUCA-Server at its session limit closes with 1013 before any agent.
    monkeypatch.setattr(SessionRuntime, "max_sessions", 0)
    client = MucaWsClient(server.url, conversation_id="channel:1", is_dm=False)

    with pytest.raises(MucaConnectionLost):
        await client.connect()

    assert not client.is_open
    assert client.close_code == 1013


async def test_spending_reaches_the_client_and_it_can_switch_replies_to_text(server):
    client = MucaWsClient(server.url, conversation_id="instance:c", is_dm=False)
    client.text_replies = True
    usages: list[dict] = []

    async def on_usage(usage: dict) -> None:
        usages.append(usage)

    client.on_usage = on_usage
    frames, done = await collect_reply(client)
    EchoMainAgent.sessions = []
    await client.connect()

    await client.send_user_text(speaker=5, speaker_name="Ada", text="costly")
    await asyncio.wait_for(done.wait(), timeout=5)
    await client.set_text_replies(False)
    await client.close()

    assert usages == [
        {
            "event": "usage",
            "agent": "main",
            "freshText": 10,
            "cachedText": 20,
            "freshAudio": 30,
            "cachedAudio": 40,
            "outText": 50,
            "outAudio": 60,
            "costUsd": 0.25,
        }
    ]
    first, second = EchoMainAgent.sessions
    assert first["output_modalities"] == ["text"]
    assert second == {"output_modalities": ["audio"]}


async def test_a_turn_skipped_frame_calls_on_no_reply():
    # No server needed -- this is purely the client's own frame dispatch.
    client = MucaWsClient("ws://unused/", conversation_id="instance:d", is_dm=False)
    calls = 0

    async def on_no_reply() -> None:
        nonlocal calls
        calls += 1

    client.on_no_reply = on_no_reply
    await client._handle_raw('{"event": "turn_skipped"}')

    assert calls == 1
