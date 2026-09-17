"""
Turns assistant_text deltas into one throttled Discord message per reply.

Ported from the old discord_adapter._dispatch_fn's buffering/throttle
behaviour, adapted from a per-turn chunk iterator to MucaWsClient's
delta/is_final event stream: on_delta is called once per server event
instead of once per chunk_iterator loop.
"""

from __future__ import annotations

import time

EDIT_THROTTLE_SECONDS = 0.75


class ReplyDispatcher:
    def __init__(self, channel) -> None:
        self._channel = channel
        self._buffer = ""
        self._sent_message = None
        self._last_edit = 0.0

    async def on_delta(self, text: str, is_final: bool) -> None:
        if is_final:
            await self._finalize()
            return

        self._buffer += text

        if self._sent_message is None:
            self._sent_message = await self._channel.send(self._buffer)
            self._last_edit = time.monotonic()
            return

        # Throttle edits so we forward the stream without hitting Discord's
        # rate limits.
        if time.monotonic() - self._last_edit > EDIT_THROTTLE_SECONDS:
            await self._sent_message.edit(content=self._buffer)
            self._last_edit = time.monotonic()

    async def _finalize(self) -> None:
        if self._sent_message is None:
            return  # the assistant produced no output

        if self._sent_message.content != self._buffer:
            await self._sent_message.edit(content=self._buffer)

        self._buffer = ""
        self._sent_message = None
