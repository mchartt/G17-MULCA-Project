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
from .instances import load_instances


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    discord_token = os.environ["DISCORD_BOT_TOKEN"]
    muca_server_url = os.environ.get("MUCA_SERVER_URL", "ws://localhost:8000/")
    instances = load_instances()

    client = build_discord_client(
        muca_server_url=muca_server_url,
        instances=instances,
    )

    try:
        client.run(discord_token)
    finally:
        asyncio.run(close_all_sessions(client))


if __name__ == "__main__":
    main()
