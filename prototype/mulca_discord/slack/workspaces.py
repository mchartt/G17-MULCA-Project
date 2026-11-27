"""
One Cadence Slack app in many workspaces.

Every workspace that pressed "Add to Slack" has its own bot token
(installs.py), and every Slack call must use the token of the workspace the
channel belongs to. Workspaces is a SlackApi (api.py) for the hub that hides
this: the hub keeps calling post(channel, ...), and Workspaces picks the right
workspace from the channel (Slack channel ids are unique across workspaces).

How it learns where a channel is:
    - every request Slack sends carries its workspace (learn(), from __main__);
    - channels() lists each workspace's channels;
    - an unknown channel reloads the installs (a workspace added a moment ago
      from the web adapter) and lists the channels again.

The old one-workspace setup still works: SLACK_BOT_TOKEN is one more
workspace, found with auth.test (add_token).
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .api import SdkSlackApi
from .installs import InstallStore

logger = logging.getLogger(__name__)


class Workspaces:
    def __init__(self, make_client: Callable[[str], Any], store: InstallStore | None = None) -> None:
        self._make_client = make_client  # token -> slack_sdk AsyncWebClient
        self._store = store
        self._apis: dict[str, SdkSlackApi] = {}  # team id -> its API
        self._tokens: dict[str, str] = {}  # team id -> token it was started with
        self._team_of: dict[str, str] = {}  # channel id -> team id
        self._from_env: set[str] = set()  # teams of SLACK_BOT_TOKEN: never dropped by reload

    # -- the workspaces ---------------------------------------------------

    async def add_token(self, token: str) -> str:
        """A workspace by its bot token (SLACK_BOT_TOKEN); returns its team id."""
        api = SdkSlackApi(self._make_client(token))
        await api.start()
        team = api.team_id or "default"
        self._apis[team] = api
        self._tokens[team] = token
        self._from_env.add(team)
        return team

    async def reload(self) -> None:
        """Start the workspaces added (or re-added) since the last time; drop removed ones."""
        if self._store is None:
            return
        installs = self._store.all()
        known = {i.team_id for i in installs}
        for install in installs:
            if self._tokens.get(install.team_id) == install.bot_token:
                continue
            api = SdkSlackApi(self._make_client(install.bot_token))
            try:
                await api.start()
            except Exception:  # a revoked token: skip it, the others keep working
                logger.warning("Slack workspace %s: its token no longer works", install.team_id)
                continue
            self._apis[install.team_id] = api
            self._tokens[install.team_id] = install.bot_token
            logger.info("Cadence is in the Slack workspace %s", install.team_name)
        # Removed from the store meanwhile (the app was uninstalled): stop using it.
        for team in [t for t in self._apis if t not in known and t not in self._from_env]:
            self.forget_team(team)

    def forget_team(self, team: str) -> None:
        """The app was removed from a workspace: no more calls there."""
        self._apis.pop(team, None)
        self._tokens.pop(team, None)
        if self._store is not None:
            self._store.remove(team)
        for channel in [c for c, t in self._team_of.items() if t == team]:
            del self._team_of[channel]

    def learn(self, channel: str, team: str) -> None:
        if channel and team:
            self._team_of[channel] = team

    @property
    def teams(self) -> list[str]:
        return list(self._apis)

    # -- SlackApi -----------------------------------------------------------

    @property
    def bot_user(self) -> str:
        """For the logs only: the hub asks is_me (one bot user per workspace)."""
        return ", ".join(api.bot_user for api in self._apis.values())

    def is_me(self, user: str) -> bool:
        return any(api.bot_user == user for api in self._apis.values())

    async def _for(self, channel: str) -> SdkSlackApi:
        team = self._team_of.get(channel)
        if team in self._apis:
            return self._apis[team]
        if len(self._apis) == 1 and self._store is None:
            return next(iter(self._apis.values()))
        await self.reload()
        await self.channels()
        team = self._team_of.get(channel)
        if team in self._apis:
            return self._apis[team]
        if len(self._apis) == 1:
            return next(iter(self._apis.values()))
        raise LookupError(f"no Slack workspace has the channel {channel}")

    async def post(self, channel: str, text: str, blocks: list[dict] | None = None) -> str:
        return await (await self._for(channel)).post(channel, text, blocks)

    async def update(self, channel: str, ts: str, text: str, blocks: list[dict] | None = None) -> None:
        await (await self._for(channel)).update(channel, ts, text, blocks)

    async def ephemeral(self, channel: str, user: str, text: str) -> None:
        await (await self._for(channel)).ephemeral(channel, user, text)

    async def roster(self, channel: str) -> dict[str, str]:
        return await (await self._for(channel)).roster(channel)

    async def channels(self) -> list[str]:
        found: list[str] = []
        for team, api in list(self._apis.items()):
            try:
                mine = await api.channels()
            except Exception:
                logger.exception("Could not list the channels of Slack workspace %s", team)
                continue
            for channel in mine:
                self._team_of[channel] = team
            found += mine
        return found
