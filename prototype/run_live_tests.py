"""
Run the cross-channel end-to-end suite LIVE, in one step (LIVE_TESTS.md).

    python run_live_tests.py            (or double-click run_live_tests.bat on Windows)

What it does, with no token ever typed or shown:
  1. reads prototype/.env and the MUCA-Server .env next to this clone (the same
     files the bots already use: Discord and Slack tokens, the Azure key);
  2. picks the test channels by itself, unless set in CADENCE_TEST_*_CHANNEL:
     Slack: the first channel the bot is a member of;
     Discord: the first text channel linked in data/mulca.db (the bot's own links);
  3. turns on the real model for everything Cadence writes (CADENCE_LIVE_MODEL);
  4. runs tests/live and writes live-report.txt (the summary is printed too).

Cadence's cards and lines appear for real in those two channels while it runs,
each tagged with a short stamp. Members are simulated (harness.py says why).
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE / "live-report.txt"


def load_env() -> list[str]:
    """Fill os.environ from the .env files the bots use; returns which files were read."""
    from dotenv import load_dotenv

    read = []
    for path in (HERE / ".env", *(HERE.parent.parent / name / ".env" for name in ("muca-server", "MUCA-Server", "G17-MULCA-Server"))):
        if path.is_file():
            load_dotenv(path, override=False)
            read.append(str(path))
    return read


async def slack_channel() -> str:
    from slack_sdk.web.async_client import AsyncWebClient

    client = AsyncWebClient(token=os.environ["SLACK_BOT_TOKEN"])
    found = await client.users_conversations(types="public_channel,private_channel", exclude_archived=True, limit=50)
    channels = found.get("channels", [])
    return channels[0]["id"] if channels else ""


def discord_channel() -> str:
    db = HERE / "data" / "mulca.db"
    if not db.is_file():
        return ""
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT text_channel_id FROM links ORDER BY rowid LIMIT 1").fetchone()
    return str(row[0]) if row else ""


def main() -> int:
    read = load_env()
    print("Read:", ", ".join(read) or "no .env found")
    if os.environ.get("SLACK_BOT_TOKEN") and not os.environ.get("CADENCE_TEST_SLACK_CHANNEL"):
        try:
            os.environ["CADENCE_TEST_SLACK_CHANNEL"] = asyncio.run(slack_channel())
        except Exception as error:  # a wrong token or a missing scope: say it, run the rest
            print("Slack: could not list the bot's channels:", error)
    if os.environ.get("DISCORD_BOT_TOKEN") and not os.environ.get("CADENCE_TEST_DISCORD_CHANNEL"):
        os.environ["CADENCE_TEST_DISCORD_CHANNEL"] = discord_channel()
    has_model = os.environ.get("AZURE_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if has_model:
        os.environ.setdefault("CADENCE_LIVE_MODEL", "1")
    print("Slack channel:", os.environ.get("CADENCE_TEST_SLACK_CHANNEL") or "none (recorded only)")
    print("Discord channel:", os.environ.get("CADENCE_TEST_DISCORD_CHANNEL") or "none (recorded only)")
    print("Model:", "real" if has_model else "scripted (no key found)")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/live", "-v", "-rA", "-p", "no:cacheprovider"],
        cwd=HERE, capture_output=True, text=True,
    )
    REPORT.write_text(result.stdout + result.stderr, encoding="utf-8")
    summary = [line for line in result.stdout.splitlines() if line.startswith(("PASSED", "FAILED", "SKIPPED", "ERROR", "="))]
    print("\n".join(summary[-45:]))
    print(f"\nFull report: {REPORT}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
