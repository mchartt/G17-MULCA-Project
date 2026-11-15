"""
Turns assistant_text deltas into one throttled Discord message per reply.

Ported from the old discord_adapter._dispatch_fn's buffering/throttle
behaviour, adapted from a per-turn chunk iterator to MucaWsClient's
delta/is_final event stream: on_delta is called once per server event
instead of once per chunk_iterator loop.

A written reply ("text" modality) is always posted. The transcript of a
spoken reply ("audio" modality) was already heard in the voice channel, so
it is only posted when the instance asks for it (post_voice_transcripts).
The two can stream at the same time, so each keeps its own message.
"""

from __future__ import annotations

import time

EDIT_THROTTLE_SECONDS = 0.75

# Discord rejects longer messages; a reply that grows past this continues
# in a follow-up message.
DISCORD_MESSAGE_LIMIT = 2000

TRANSCRIPT_PREFIX = "\N{SPEAKER WITH THREE SOUND WAVES} "


class _Reply:
    """One reply being streamed into one or more Discord messages."""

    def __init__(self, channel, *, prefix: str = "") -> None:
        self._channel = channel
        self._prefix = prefix
        self._buffer = ""
        # Text already committed to earlier, full messages.
        self._committed = 0
        self._sent_message = None
        self._last_edit = 0.0

    async def add(self, text: str) -> None:
        self._buffer += text
        await self._flush(force=False)

    async def finish(self) -> None:
        await self._flush(force=True)

    async def _flush(self, *, force: bool) -> None:
        while True:
            pending = self._buffer[self._committed:]
            content = self._prefix + pending if pending else ""

            if not content.strip():
                # Nothing visible to show yet (Discord rejects empty sends).
                return

            if len(content) > DISCORD_MESSAGE_LIMIT:
                # Cut at a space near the limit, so words stay whole.
                budget = DISCORD_MESSAGE_LIMIT - len(self._prefix)
                cut = pending.rfind(" ", 0, budget)
                if cut <= 0:
                    cut = budget

                await self._show(self._prefix + pending[:cut])
                self._committed += cut
                self._sent_message = None
                continue

            if self._sent_message is None:
                self._sent_message = await self._channel.send(content)
                self._last_edit = time.monotonic()
                return

            # Throttle edits so we forward the stream without hitting
            # Discord's rate limits.
            stale = self._sent_message.content != content
            if stale and (
                force
                or time.monotonic() - self._last_edit > EDIT_THROTTLE_SECONDS
            ):
                await self._sent_message.edit(content=content)
                self._last_edit = time.monotonic()
            return

    async def _show(self, content: str) -> None:
        if self._sent_message is None:
            await self._channel.send(content)
        elif self._sent_message.content != content:
            await self._sent_message.edit(content=content)


class ReplyDispatcher:
    def __init__(
        self,
        channel,
        *,
        post_voice_transcripts: bool = False,
    ) -> None:
        self._channel = channel
        self.post_voice_transcripts = post_voice_transcripts
        self._replies: dict[str, _Reply] = {}

    @property
    def channel(self):
        return self._channel

    async def on_delta(
        self,
        text: str,
        is_final: bool,
        modality: str = "text",
    ) -> None:
        if modality == "audio" and not self.post_voice_transcripts:
            return

        if self._channel is None:
            return

        reply = self._replies.get(modality)
        if reply is None:
            reply = _Reply(
                self._channel,
                prefix=TRANSCRIPT_PREFIX if modality == "audio" else "",
            )
            self._replies[modality] = reply

        if text:
            await reply.add(text)

        if is_final:
            await reply.finish()
            del self._replies[modality]
