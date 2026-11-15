"""
Run the web adapter on its own:  python -m mulca_discord.web

    MUCA_SERVER_URL   MUCA-Server WebSocket (default ws://localhost:8000/)
    MULCA_WEB_HOST    default 127.0.0.1 (only this computer)
    MULCA_WEB_PORT    default 8080
    MULCA_WEB_DB      default data/web.sqlite3 (data/ is git-ignored)
    MULCA_WEB_STATIC  built frontend, default webapp/dist
    MULCA_WEB_FILM    film frames, default webapp/film/public
    MULCA_WEB_ALLOWED_ORIGINS  comma-separated origins of a frontend hosted elsewhere (optional)

Needs no Discord token: useful for the web-only demo and for development.
Running it inside the Discord process (same event loop) is assumption A5 in
PROGRESS.md and is not wired yet.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from .app import create_web_app
from .hub import WebHub
from .store import WebStore

HERE = Path(__file__).resolve().parents[2]  # prototype/


def main() -> None:
    load_dotenv()
    logging.basicConfig(level="INFO")
    db = Path(os.environ.get("MULCA_WEB_DB", HERE / "data" / "web.sqlite3"))
    db.parent.mkdir(parents=True, exist_ok=True)
    hub = WebHub(WebStore(db), os.environ.get("MUCA_SERVER_URL", "ws://localhost:8000/"))
    app = create_web_app(
        hub,
        static_dir=os.environ.get("MULCA_WEB_STATIC", HERE / "webapp" / "dist"),
        film_dir=os.environ.get("MULCA_WEB_FILM", HERE / "webapp" / "film" / "public"),
        allowed_origins=[o.strip() for o in os.environ.get("MULCA_WEB_ALLOWED_ORIGINS", "").split(",") if o.strip()],
    )
    config = uvicorn.Config(
        app,
        host=os.environ.get("MULCA_WEB_HOST", "127.0.0.1"),
        port=int(os.environ.get("MULCA_WEB_PORT", "8080")),
        log_level="info",
        # The access log would print every URL, including the secret of a
        # calendar feed (/api/calendar/<secret>.ics): off (M5 review).
        access_log=False,
    )

    async def run() -> None:
        try:
            await uvicorn.Server(config).serve()
        finally:
            await hub.close()

    asyncio.run(run())


if __name__ == "__main__":
    main()
