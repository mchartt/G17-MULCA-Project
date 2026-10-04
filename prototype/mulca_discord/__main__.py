"""
Runs the MULCA Discord adapter against a MUCA-Server instance.

Replaces the old `manage.py run_discord_bot` management command -- no
Django, no ORM, nothing but a Discord client and a WebSocket connection.

Run with: python -m mulca_discord
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from contextlib import suppress

from dotenv import load_dotenv

from .commands import install_commands
from .discord_client import build_discord_client, close_all_sessions
from .links import LinkStore, configured_db_path
from .runtime import BotManager
from .singleton import AlreadyRunning, acquire_singleton_lock


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    # Logs every RTCP sender report Discord sends (several a second in voice)
    # at INFO as "unexpected"; they're routine and bury the useful lines.
    logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.WARNING)

    try:
        # Held for the rest of the process's life -- see singleton.py for
        # why this matters (two processes on one bot token both answer
        # every message, silently, with no error from Discord itself).
        _lock = acquire_singleton_lock()  # noqa: F841
    except AlreadyRunning as exc:
        logging.error(str(exc))
        sys.exit(1)

    discord_token = os.environ["DISCORD_BOT_TOKEN"]
    muca_server_url = os.environ.get("MUCA_SERVER_URL", "ws://localhost:8000/")
    db_path = configured_db_path()
    logging.info("Links and bot state in %s", db_path)
    store = LinkStore(db_path)

    client = build_discord_client(
        muca_server_url=muca_server_url,
        store=store,
    )
    # The primary bot (this token, a Swarm secret) carries the slash
    # commands; bots added with /mulca bot add run beside it, in this process.
    manager = BotManager(
        [client.mulca_runtime],
        store=store,
        client_factory=lambda: build_discord_client(
            muca_server_url=muca_server_url,
            store=store,
            is_primary=False,
        ),
        primary_token=discord_token,
    )
    install_commands(manager)

    async def shutdown() -> None:
        await manager.stop_added_bots()
        await client.close()

    async def run() -> None:
        # Swarm stops a container with SIGTERM: log out and close the
        # sessions (MUCA-Server saves each conversation as its session
        # ends) instead of dying mid-conversation. Not on Windows, which
        # has no add_signal_handler; Ctrl+C still works there.
        with suppress(NotImplementedError):
            asyncio.get_running_loop().add_signal_handler(
                signal.SIGTERM,
                lambda: asyncio.ensure_future(shutdown()),
            )

        # One event loop for the bots and their MUCA-Server sessions, so the
        # sessions can still be closed (with a disconnect) on the way out.
        async with client:
            await manager.start_added_bots()
            try:
                await client.start(discord_token)
            finally:
                await manager.stop_added_bots()
                await close_all_sessions(client)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
