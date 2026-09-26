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

from dotenv import load_dotenv

from .discord_client import build_discord_client, close_all_sessions
from .instances import configured_instances_path, load_instances


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    discord_token = os.environ["DISCORD_BOT_TOKEN"]
    muca_server_url = os.environ.get("MUCA_SERVER_URL", "ws://localhost:8000/")
    instances_path = configured_instances_path()
    logging.info("Instances from %s", instances_path)
    instances = load_instances(instances_path)

    client = build_discord_client(
        muca_server_url=muca_server_url,
        instances=instances,
    )

    async def run() -> None:
        # One event loop for the bot and its MUCA-Server sessions, so the
        # sessions can still be closed (with a disconnect) on the way out.
        async with client:
            try:
                await client.start(discord_token)
            finally:
                await close_all_sessions(client)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
