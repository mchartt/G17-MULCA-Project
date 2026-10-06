"""
The Discord half of the adapter.

Everything here is unchanged in spirit from the old (deleted) discord_adapter
module: bot-author filtering, DM detection, the roster-from-channel.members
lookup. What changed is what it's wired to -- a MUCA-Server session per
scope (sessions.py) instead of an in-process Orchestrator, and scoping is
driven by the channels linked to this bot from Discord (links.py, /mulca
link): a linked text channel and its paired voice channel share one scope,
one memory. The event handlers themselves live on BotRuntime (runtime.py),
which the slash commands (commands.py) also drive.

Voice: whenever someone is in a linked voice channel, MULCA is there too,
listening (voice/). It leaves when the channel empties.
"""

from __future__ import annotations

import logging

import discord

from .links import LinkStore
from .runtime import BotRuntime, _humans, _roster
from .sessions import SessionRegistry

logger = logging.getLogger(__name__)

__all__ = [
    "build_discord_client",
    "close_all_sessions",
    "mulca_intents",
    "_humans",
    "_roster",
]


def mulca_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    # Needed for channel.members / _roster to see participants who haven't
    # spoken yet -- also requires the "Server Members Intent" toggle enabled
    # in the Discord Developer Portal.
    intents.members = True
    # Who joins and leaves the voice channels (on by default; explicit here
    # because voice depends on it).
    intents.voice_states = True
    return intents


def build_discord_client(
    *,
    muca_server_url: str,
    store: LinkStore,
    registry: SessionRegistry | None = None,
    is_primary: bool = True,
) -> discord.Client:
    """
    `client.mulca_runtime` is the BotRuntime handling this client's events;
    `client.mulca_sessions` holds the MUCA-Server session of each scope (a
    linked channel's "channel:<id>", or "dm:<user_id>"), opened lazily on
    first use and reopened if MUCA-Server went away.
    """

    client = discord.Client(intents=mulca_intents())
    runtime = BotRuntime(
        client=client,
        registry=registry
        or SessionRegistry(
            muca_server_url,
            # Read at each connect, so a /mulca model change reaches the
            # next session without rebuilding anything.
            models=lambda: store.models_for(client.user and client.user.id),
        ),
        store=store,
        is_primary=is_primary,
    )
    runtime.install()

    client.mulca_runtime = runtime
    client.mulca_sessions = runtime.registry
    client.mulca_voice = runtime.voice
    return client


async def close_all_sessions(client: discord.Client) -> None:
    await client.mulca_runtime.close()
