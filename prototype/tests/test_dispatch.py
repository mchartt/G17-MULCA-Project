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
