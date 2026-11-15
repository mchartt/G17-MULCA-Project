from mulca_discord.dispatch import ReplyDispatcher


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.edits: list[str] = []

    async def edit(self, content: str) -> None:
        self.edits.append(content)
        self.content = content


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[FakeMessage] = []

    async def send(self, content: str) -> FakeMessage:
        message = FakeMessage(content)
        self.sent.append(message)
        return message


async def test_the_first_delta_sends_one_message():
    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel)

    await dispatcher.on_delta("Hello", False)

    assert [m.content for m in channel.sent] == ["Hello"]


async def test_rapid_deltas_are_throttled_into_no_extra_edits():
    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel)

    await dispatcher.on_delta("Hello", False)
    await dispatcher.on_delta(" there", False)

    assert len(channel.sent) == 1
    assert channel.sent[0].edits == []


async def test_an_edit_is_sent_once_the_throttle_window_has_passed(monkeypatch):
    import mulca_discord.dispatch as dispatch_module

    clock = [0.0]
    monkeypatch.setattr(dispatch_module.time, "monotonic", lambda: clock[0])

    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel)

    await dispatcher.on_delta("Hello", False)
    clock[0] += 1.0
    await dispatcher.on_delta(" there", False)

    assert channel.sent[0].edits == ["Hello there"]


async def test_the_final_frame_flushes_the_buffer():
    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel)

    await dispatcher.on_delta("Hello", False)
    await dispatcher.on_delta(" there", False)
    await dispatcher.on_delta("", True)

    assert channel.sent[0].content == "Hello there"


async def test_no_output_means_no_message_sent():
    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel)

    await dispatcher.on_delta("", True)

    assert channel.sent == []


async def test_a_second_reply_starts_a_fresh_buffer():
    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel)

    await dispatcher.on_delta("First", False)
    await dispatcher.on_delta("", True)
    await dispatcher.on_delta("Second", False)
    await dispatcher.on_delta("", True)

    assert [m.content for m in channel.sent] == ["First", "Second"]


async def test_a_spoken_replys_transcript_is_not_posted_by_default():
    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel)

    await dispatcher.on_delta("I said this out loud", False, "audio")
    await dispatcher.on_delta("", True, "audio")

    assert channel.sent == []


async def test_a_spoken_replys_transcript_is_posted_when_asked_for():
    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel, post_voice_transcripts=True)

    await dispatcher.on_delta("out loud", False, "audio")
    await dispatcher.on_delta("", True, "audio")

    assert len(channel.sent) == 1
    assert channel.sent[0].content.endswith("out loud")


async def test_a_written_and_a_spoken_reply_stream_into_separate_messages():
    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel, post_voice_transcripts=True)

    await dispatcher.on_delta("written", False, "text")
    await dispatcher.on_delta("spoken", False, "audio")
    await dispatcher.on_delta("", True, "text")
    await dispatcher.on_delta("", True, "audio")

    assert len(channel.sent) == 2
    assert channel.sent[0].content == "written"
    assert channel.sent[1].content.endswith("spoken")


async def test_a_blank_delta_never_sends_an_empty_message():
    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel)

    await dispatcher.on_delta("   ", False)
    await dispatcher.on_delta("", True)

    assert channel.sent == []


async def test_a_reply_longer_than_discord_allows_continues_in_a_new_message():
    from mulca_discord.dispatch import DISCORD_MESSAGE_LIMIT

    channel = FakeChannel()
    dispatcher = ReplyDispatcher(channel)
    words = "word " * 900  # 4500 characters

    await dispatcher.on_delta(words, False)
    await dispatcher.on_delta("", True)

    assert len(channel.sent) == 3
    assert all(len(m.content) <= DISCORD_MESSAGE_LIMIT for m in channel.sent)
    assert "".join(m.content for m in channel.sent).split() == words.split()
