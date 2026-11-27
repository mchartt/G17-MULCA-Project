"""
Run the Slack channel:  python -m mulca_discord.slack

Slack reaches the bot through Socket Mode: the bot opens a WebSocket to Slack,
so it needs no public address (it works on a laptop and on Render alike).

Environment (prototype/.env):
    SLACK_APP_TOKEN   xapp-...  the app-level token with connections:write (Socket Mode)
    SLACK_BOT_TOKEN   xoxb-...  optional: one workspace's bot token (the old setup)
    MUCA_SERVER_URL   where MUCA-Server listens (default ws://localhost:8000/)

Workspaces added with the web app's "Add to Slack" button are read from the
install store (installs.py, written by web/connect_routes.py): one app, many
workspaces, no token to copy for the groups (workspaces.py).

How to create the Slack app once: SLACK_SETUP.md.

Slack sends three kinds of request; each is acknowledged at once (Slack wants
an answer within 3 seconds) and then handled in the background:
    events_api      a message in a channel        -> SlackHub.on_message
    slash_commands  /coordinator ...              -> SlackHub.on_command
    interactive     a button on a card            -> SlackHub.on_action
"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv

from .api import SdkSlackApi
from .hub import SlackHub
from .installs import InstallStore
from .workspaces import Workspaces

logger = logging.getLogger(__name__)

RELOAD_SECONDS = 60


def team_of(kind: str, payload: dict) -> str:
    """The workspace a Slack request comes from."""
    if kind == "interactive":
        return (payload.get("team") or {}).get("id", "")
    return payload.get("team_id", "")


def channel_of(kind: str, payload: dict) -> str:
    if kind == "events_api":
        return (payload.get("event") or {}).get("channel", "")
    if kind == "interactive":
        return (payload.get("channel") or {}).get("id", "")
    return payload.get("channel_id", "")


async def handle(hub: SlackHub, api: Workspaces | SdkSlackApi, kind: str, payload: dict) -> None:
    """One Slack request, after it was acknowledged. Private answers go back as ephemeral messages."""
    if isinstance(api, Workspaces):
        api.learn(channel_of(kind, payload), team_of(kind, payload))
    if kind == "events_api":
        event = payload.get("event", {})
        if event.get("type") in ("app_uninstalled", "tokens_revoked") and isinstance(api, Workspaces):
            # The workspace removed Cadence: its token is deleted (installs.py).
            api.forget_team(team_of(kind, payload))
        elif event.get("type") == "message":
            await hub.on_message(event)
        elif event.get("type") == "member_joined_channel":
            await hub.on_joined(event)
    elif kind == "slash_commands":
        channel, user = payload.get("channel_id", ""), payload.get("user_id", "")
        is_dm = payload.get("channel_name") == "directmessage"
        text = await hub.on_command(channel, user, payload.get("text", ""), is_dm=is_dm)
        await api.ephemeral(channel, user, text)
    elif kind == "interactive" and payload.get("type") == "block_actions":
        channel = payload.get("channel", {}).get("id", "")
        user = payload.get("user", {}).get("id", "")
        ts = payload.get("container", {}).get("message_ts", "")
        for action in payload.get("actions", []):
            await api.ephemeral(channel, user, await hub.on_action(channel, user, action.get("action_id", ""), ts))


async def run() -> None:
    # Imported here: only this entry point needs the Slack SDK installed.
    from slack_sdk.socket_mode.aiohttp import SocketModeClient
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.web.async_client import AsyncWebClient

    api = Workspaces(lambda token: AsyncWebClient(token=token), InstallStore())
    if os.environ.get("SLACK_BOT_TOKEN"):
        await api.add_token(os.environ["SLACK_BOT_TOKEN"])
    await api.reload()
    hub = SlackHub(api, os.environ.get("MUCA_SERVER_URL", "ws://localhost:8000/"))
    # Socket Mode needs only the app-level token; each call uses its workspace's token.
    socket = SocketModeClient(app_token=os.environ["SLACK_APP_TOKEN"], web_client=AsyncWebClient())

    async def on_request(client, request) -> None:
        await client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))

        async def work() -> None:
            try:
                await handle(hub, api, request.type, request.payload)
            except Exception:  # one bad request must not stop the bot
                logger.exception("Slack request %s failed", request.type)

        asyncio.create_task(work())

    socket.socket_mode_request_listeners.append(on_request)
    await socket.connect()
    logger.info("Cadence is connected to Slack in %d workspace(s)", len(api.teams))
    # Every channel the bot is in listens from now on, so a card made on the web
    # or on Discord shows here too even if nobody wrote on Slack yet.
    opened = await hub.warm_up()
    logger.info("Cadence is listening in %d Slack channel(s)", len(opened))
    try:
        while True:  # until Ctrl+C; a workspace added from the web starts within a minute
            await asyncio.sleep(RELOAD_SECONDS)
            try:
                before = set(api.teams)
                await api.reload()
                if set(api.teams) - before:
                    await hub.warm_up()
            except Exception:
                logger.exception("Could not reload the Slack workspaces")
    finally:
        await socket.close()
        await hub.close()


def main() -> None:
    load_dotenv()
    logging.basicConfig(level="INFO")
    asyncio.run(run())


if __name__ == "__main__":
    main()
