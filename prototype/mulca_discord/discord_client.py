"""
The Discord half of the adapter.

Everything here is unchanged in spirit from the old (deleted) discord_adapter
module: bot-author filtering, DM detection, the roster-from-channel.members
lookup. What changed is what it's wired to -- a MucaWsClient session per
scope instead of an in-process Orchestrator, and scoping is now driven by
the configured MulcaInstance list (instances.py) instead of a flat
MULCA_CHANNEL_IDS allowlist, so a text channel and its paired voice channel
share one scope/one memory once voice exists, not just one channel each.
"""

from __future__ import annotations

import asyncio
import logging

import discord

from .dispatch import ReplyDispatcher
from .instances import MulcaInstance, instance_for_channel
from .muca_client import MucaWsClient

logger = logging.getLogger(__name__)


async def _roster(channel: discord.abc.Messageable) -> dict[int, str]:
    members = getattr(channel, "members", [])
    return {member.id: member.display_name for member in members if not member.bot}


def build_discord_client(
    *,
    muca_server_url: str,
    instances: list[MulcaInstance],
) -> discord.Client:
    """
    `sessions` maps scope (a MulcaInstance's conversation_id, or
    "dm:<user_id>") to its MucaWsClient + ReplyDispatcher, both created
    lazily on first use for that scope, exactly as the old Orchestrator
    keyed its WM/session per scope.
    """

    intents = discord.Intents.default()
    intents.message_content = True
    # Needed for channel.members / _roster to see participants who haven't
    # spoken yet -- also requires the "Server Members Intent" toggle enabled
    # in the Discord Developer Portal.
    intents.members = True

    client = discord.Client(intents=intents)
    sessions: dict[str, tuple[MucaWsClient, ReplyDispatcher]] = {}
    client.mulca_sessions = sessions
    # discord.py runs on_message concurrently, so two messages for the same
    # scope arriving before the first connect() resolves would otherwise both
    # see "no existing session" and each stand up a duplicate one -- this
    # lock makes check-then-create-then-store atomic across those calls.
    sessions_lock = asyncio.Lock()

    async def _session_for(
        scope: str,
        *,
        is_dm: bool,
        channel: discord.abc.Messageable,
    ) -> MucaWsClient:
        async with sessions_lock:
            existing = sessions.get(scope)
            if existing is not None:
                return existing[0]

            muca_client = MucaWsClient(
                muca_server_url,
                conversation_id=scope,
                is_dm=is_dm,
            )
            dispatcher = ReplyDispatcher(channel)
            muca_client.on_assistant_text = dispatcher.on_delta

            await muca_client.connect()
            asyncio.create_task(muca_client.receive_loop())

            sessions[scope] = (muca_client, dispatcher)
            return muca_client

    @client.event
    async def on_ready() -> None:
        logger.info(
            "MULCA text bot logged in as %s (id=%s)",
            client.user,
            client.user.id,
        )

    @client.event
    async def on_message(message: discord.Message) -> None:
        logger.debug(
            "on_message: author_id=%s is_bot=%s channel_id=%s content=%r",
            message.author.id,
            message.author.bot,
            message.channel.id,
            message.content,
        )

        if message.author.bot:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)

        if is_dm:
            # Permissive by design (BLUEPRINT.md: "open to DMs from any
            # individual user") -- not gated on any instance's
            # participant_ids, which document team membership, not access.
            scope = f"dm:{message.author.id}"
        else:
            instance = instance_for_channel(instances, message.channel.id)
            if instance is None:
                # Not a channel any configured MulcaInstance owns.
                return
            scope = instance.conversation_id

        muca_client = await _session_for(scope, is_dm=is_dm, channel=message.channel)

        if not is_dm:
            roster = await _roster(message.channel)
            await muca_client.send_participants(roster)

        await muca_client.send_user_text(
            speaker=message.author.id,
            speaker_name=message.author.display_name,
            text=message.content,
        )

    return client


async def close_all_sessions(client: discord.Client) -> None:
    for muca_client, _ in client.mulca_sessions.values():
        await muca_client.close()
