"""
The few Slack calls the hub needs, behind one small interface.

SlackApi is what hub.py talks to (a Protocol: any object with these methods).
SdkSlackApi is the real one, a thin wrapper over slack_sdk's AsyncWebClient.
The tests use a fake with the same methods, so the hub is tested without
Slack and without the network (the Adapter pattern: the hub never sees the
shape of Slack's own responses).
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from ..names import unique_in_channel

ROSTER_SECONDS = 300  # how long a channel's member list is reused


class SlackApi(Protocol):
    bot_user: str  # the bot's own Slack user id, e.g. "U0BOT"

    async def post(self, channel: str, text: str, blocks: list[dict] | None = None) -> str:
        """Post in the channel; returns the message's timestamp (its id on Slack)."""
        ...

    async def update(self, channel: str, ts: str, text: str, blocks: list[dict] | None = None) -> None: ...

    async def ephemeral(self, channel: str, user: str, text: str) -> None:
        """A message only this user sees."""
        ...

    async def roster(self, channel: str) -> dict[str, str]:
        """The people in the channel (no bots): Slack user id -> name."""
        ...

    async def channels(self) -> list[str]:
        """The channels the bot is a member of (public and private), by id."""
        ...


class SdkSlackApi:
    def __init__(self, client: Any) -> None:
        self._client = client  # slack_sdk.web.async_client.AsyncWebClient
        self.bot_user = ""
        self._rosters: dict[str, tuple[float, dict[str, str]]] = {}
        self._names: dict[str, str | None] = {}  # user id -> name, None for a bot

    async def start(self) -> None:
        """Ask Slack who the bot is (also checks the token)."""
        self.bot_user = (await self._client.auth_test())["user_id"]

    async def post(self, channel: str, text: str, blocks: list[dict] | None = None) -> str:
        response = await self._client.chat_postMessage(channel=channel, text=text, blocks=blocks, unfurl_links=False)
        return response["ts"]

    async def update(self, channel: str, ts: str, text: str, blocks: list[dict] | None = None) -> None:
        await self._client.chat_update(channel=channel, ts=ts, text=text, blocks=blocks)

    async def ephemeral(self, channel: str, user: str, text: str) -> None:
        await self._client.chat_postEphemeral(channel=channel, user=user, text=text)

    async def roster(self, channel: str) -> dict[str, str]:
        cached = self._rosters.get(channel)
        if cached and time.monotonic() - cached[0] < ROSTER_SECONDS:
            return cached[1]
        members = (await self._client.conversations_members(channel=channel, limit=200))["members"]
        roster = {}
        for user in members:
            name = await self._name(user)
            if name is not None:
                roster[user] = name
        # Two people with the same name are two names for the model (names.py).
        roster = unique_in_channel(roster)
        self._rosters[channel] = (time.monotonic(), roster)
        return roster

    async def channels(self) -> list[str]:
        found: list[str] = []
        cursor = None
        while True:
            response = await self._client.users_conversations(
                types="public_channel,private_channel", exclude_archived=True, limit=200, cursor=cursor
            )
            found += [channel["id"] for channel in response.get("channels", [])]
            cursor = (response.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return found

    async def _name(self, user: str) -> str | None:
        if user not in self._names:
            info = (await self._client.users_info(user=user))["user"]
            profile = info.get("profile", {})
            name = profile.get("display_name") or info.get("real_name") or info.get("name") or "member"
            self._names[user] = None if info.get("is_bot") or info.get("deleted") else name
        return self._names[user]
