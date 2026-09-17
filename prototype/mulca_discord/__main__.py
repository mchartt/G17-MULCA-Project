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


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    discord_token = os.environ["DISCORD_BOT_TOKEN"]
    muca_server_url = os.environ.get("MUCA_SERVER_URL", "ws://localhost:8000/")
    channel_ids_raw = os.environ.get("MULCA_CHANNEL_IDS", "").strip()
    channel_ids = {c.strip() for c in channel_ids_raw.split(",") if c.strip()} or None

    client = build_discord_client(
        muca_server_url=muca_server_url,
        channel_ids=channel_ids,
    )

    try:
        client.run(discord_token)
    finally:
        asyncio.run(close_all_sessions(client))


if __name__ == "__main__":
    main()
